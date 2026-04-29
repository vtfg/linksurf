import json

import pika
from dotenv import load_dotenv

load_dotenv()

from linksurf.constants import QUEUE_MAX_PRIORITY, QUEUE_NAME
from linksurf.helpers import get_env
from linksurf.models import HttpInfo, SubmitResultBody
from linksurf.worker.client import FrontierClient
from linksurf.worker.fetcher import Fetcher
from linksurf.worker.parser import HTMLParser

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")


def run() -> None:
    client = FrontierClient()
    fetcher = Fetcher()

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments={"x-max-priority": QUEUE_MAX_PRIORITY})
    channel.basic_qos(prefetch_count=1)

    def on_message(ch, method, properties, body):
        data = json.loads(body)
        url = data["url"]
        depth = data["depth"]

        print(f"Crawling {url}")

        try:
            slot = client.reserve_slot(url)

            if slot.delay_ms > 0:
                connection.sleep(slot.delay_ms / 1000)

            response = fetcher.fetch(url)

            if response.status_code != 200:
                print(f"Skipping {url}: status {response.status_code}")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            content_type = response.headers.get("Content-Type", "")

            if "text/html" not in content_type.lower():
                print(f"Skipping {url}: not HTML")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            page, links = HTMLParser.parse(url, response.text)

            print(f"Found {len(links)} links on {url}")

            type_ = content_type.split(";")[0].strip().split("/")[-1]

            http = HttpInfo(
                status_code=response.status_code,
                size=len(response.content),
                response_time=int(response.elapsed.total_seconds() * 1000),
            )

            upload = client.get_presigned_upload_url(url)
            client.upload_html(upload.presigned_url, response.text)

            client.submit_result(SubmitResultBody(
                address=url,
                depth=depth,
                content_key=upload.key,
                http=http,
                headers=dict(response.headers),
                type=type_,
                page=page,
                links=links,
            ))

            ch.basic_ack(delivery_tag=method.delivery_tag)

            print(f"Done {url}")
        except Exception as e:
            print(f"Error crawling {url}: {e}")

            ch.basic_ack(delivery_tag=method.delivery_tag)

            ch.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2, priority=properties.priority),
            )

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=False)

    print("Worker started")

    channel.start_consuming()


if __name__ == "__main__":
    run()
