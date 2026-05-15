import json
import time
from datetime import datetime, timezone

import pika
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


def run() -> None:
    client = ManagerClient()
    fetcher = Fetcher()

    domain_last_crawled: dict[str, float] = {}

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

    channel = connection.channel()

    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type="x-consistent-hash",
        durable=True,
    )

    channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments={"x-max-priority": QUEUE_MAX_PRIORITY})

    channel.queue_bind(
        queue=QUEUE_NAME,
        exchange=EXCHANGE_NAME,
        routing_key="1",
    )

    channel.basic_qos(prefetch_count=1)

    def on_message(ch, method, properties, body):
        data = json.loads(body)
        url = data["url"]
        depth = data["depth"]

        print(f"Crawling {url}")

        domain = get_domain_name(url)

        try:
            last = domain_last_crawled.get(domain)
            wait = CRAWL_DELAY - (time.time() - last) if last else 0.0

            if wait > 0:
                print(f"Sleeping {wait:.2f}s for politeness")

                connection.sleep(wait)
            elif last:
                print(f"No wait needed (last crawled {time.time() - last:.2f}s ago)")
            else:
                print(f"First worker crawl for domain")

            proxy = client.get_proxy()

            print(f"Using proxy {proxy}")

            response = fetcher.fetch(url, proxy)

            crawled_at = datetime.now(timezone.utc)
            domain_last_crawled[domain] = time.time()

            if response.status_code != 200:
                print(f"Skipping {url} -> status {response.status_code}")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            content_type = response.headers.get("Content-Type", "").lower()

            if "text/html" not in content_type:
                print(f"Skipping {url} -> not HTML")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            page, links = HTMLParser.parse(url, response.text)

            print(f"Found {len(links)} links on {url}")

            http = HttpInfo(
                status_code=response.status_code,
                size=len(response.content),
                response_time=int(response.elapsed.total_seconds() * 1000),
            )

            upload_data = client.get_presigned_upload_url(url)
            client.upload_html(upload_data.presigned_url, response.text)

            client.submit_result(SubmitResultBody(
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

            ch.basic_ack(delivery_tag=method.delivery_tag)

            print(f"Done {url}")
        except Exception as e:
            print(f"Error crawling {url} -> {e}")

            ch.basic_ack(delivery_tag=method.delivery_tag)

            ch.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=get_domain_name(url),
                body=body,
                properties=pika.BasicProperties(delivery_mode=2, priority=properties.priority),
            )

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=False)

    print(f"Worker {WORKER_ID} started, listening on {QUEUE_NAME}")

    channel.start_consuming()


if __name__ == "__main__":
    run()
