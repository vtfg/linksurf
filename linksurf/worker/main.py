import asyncio
import json
import time
import traceback
from datetime import datetime, timezone

import aio_pika
from dotenv import load_dotenv

load_dotenv()

from linksurf.constants import EXCHANGE_NAME, QUEUE_MAX_PRIORITY, QUEUE_NAME_PREFIX
from linksurf.helpers import get_domain_name, get_env
from linksurf.models import HttpInfo, SubmitResultBody
from linksurf.worker.client import ManagerClient
from linksurf.worker.fetcher import Fetcher
from linksurf.worker.parser import HTMLParser

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")
WORKER_ID = get_env("WORKER_ID", int)
QUEUE_NAME = f"{QUEUE_NAME_PREFIX}.{WORKER_ID}"
CRAWL_DELAY = 2.0
MAX_COROUTINES = 10


async def run() -> None:
    client = ManagerClient()
    fetcher = Fetcher()

    domain_locks: dict[str, asyncio.Lock] = {}
    domain_last_crawled: dict[str, float] = {}
    semaphore = asyncio.Semaphore(MAX_COROUTINES)

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=MAX_COROUTINES)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        type="x-consistent-hash",
        durable=True,
    )

    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={"x-max-priority": QUEUE_MAX_PRIORITY},
    )

    await queue.bind(exchange, routing_key="1")

    async def process(message: aio_pika.IncomingMessage) -> None:
        async with semaphore:
            async with message.process():
                data = json.loads(message.body)
                url = data["url"]
                depth = data["depth"]
                domain = get_domain_name(url)

                print(f"Crawling {url}")

                if domain not in domain_locks:
                    domain_locks[domain] = asyncio.Lock()

                try:
                    async with domain_locks[domain]:
                        last = domain_last_crawled.get(domain)
                        wait = CRAWL_DELAY - (time.time() - last) if last else 0.0

                        if wait > 0:
                            print(f"Sleeping {wait:.2f}s for politeness")

                            await asyncio.sleep(wait)
                        elif last:
                            print(f"No wait needed (last crawled {time.time() - last:.2f}s ago)")
                        else:
                            print(f"First worker crawl for domain")

                        proxy = await client.get_proxy()

                        print(f"Using proxy {proxy}")

                        response = await fetcher.fetch(url, proxy)

                        crawled_at = datetime.now(timezone.utc)
                        domain_last_crawled[domain] = time.time()

                    if response.status_code != 200:
                        print(f"Skipping {url} -> status {response.status_code}")
                        return

                    content_type = response.headers.get("content-type", "").lower()

                    if "text/html" not in content_type:
                        print(f"Skipping {url} -> not HTML")
                        return

                    page, links = await asyncio.get_event_loop().run_in_executor(
                        None, HTMLParser.parse, url, response.text
                    )

                    print(f"Found {len(links)} links on {url}")

                    http = HttpInfo(
                        status_code=response.status_code,
                        size=len(response.content),
                        response_time=int(response.elapsed.total_seconds() * 1000),
                    )

                    upload_data = await client.get_presigned_upload_url(url)
                    await client.upload_html(upload_data.presigned_url, response.text)

                    await client.submit_result(SubmitResultBody(
                        address=url,
                        depth=depth,
                        content_key=upload_data.key,
                        http=http,
                        headers=dict(response.headers),
                        type=content_type.split(";")[0].strip().split("/")[-1],
                        page=page,
                        links=links,
                        crawled_at=crawled_at,
                    ))

                    print(f"Done {url}")

                except Exception:
                    print(f"Error crawling {url} ->\n{traceback.format_exc()}")

                    await exchange.publish(
                        aio_pika.Message(
                            body=message.body,
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            priority=message.priority - 1 or 0,
                        ),
                        routing_key=domain,
                    )

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        asyncio.create_task(process(message))

    await queue.consume(on_message)

    print(f"Worker {WORKER_ID} started, listening on {QUEUE_NAME}")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(run())
