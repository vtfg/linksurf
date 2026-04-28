import json

import pika
from dotenv import load_dotenv

load_dotenv()

from linksurf.constants import QUEUE_NAME
from linksurf.helpers import get_env
from linksurf.models import SubmitResultBody
from linksurf.worker.client import FrontierClient
from linksurf.worker.fetcher import Fetcher
from linksurf.worker.parser import HTMLParser

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")


def run() -> None:
    client = FrontierClient()
    fetcher = Fetcher()

    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)

    def on_message(ch, method, _properties, body):
        data = json.loads(body)
        url = data["url"]
        depth = data["depth"]

        print(f"Crawling {url}")

        try:
            slot = client.reserve_slot(url)

            if slot.delay_ms > 0:
                connection.sleep(slot.delay_ms / 1000)

            resp = fetcher.fetch(url)

            if resp.status_code != 200:
                print(f"Skipping {url}: status {resp.status_code}")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            if "text/html" not in resp.headers.get("Content-Type", "").lower():
                print(f"Skipping {url}: not HTML")

                ch.basic_ack(delivery_tag=method.delivery_tag)

                return

            metadata, links = HTMLParser.parse(url, resp.text)

            print(f"Found {len(links)} links on {url}")

            upload = client.get_presigned_upload_url(url)
            client.upload_html(upload.presigned_url, resp.text)

            client.submit_result(SubmitResultBody(
                url=url,
                depth=depth,
                html_key=upload.key,
                metadata=metadata,
                links=links,
            ))

            ch.basic_ack(delivery_tag=method.delivery_tag)

            print(f"Done {url}")
        except Exception as e:
            print(f"Error crawling {url}: {e}")

            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=False)

    print("Worker started")

    channel.start_consuming()


if __name__ == "__main__":
    run()
