import json
from typing import Any, Callable

import pika
import pika.spec
from pika.adapters.blocking_connection import BlockingChannel

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_QUEUE_PRIORITY, MIN_QUEUE_PRIORITY
from linksurf.common.payload import Payload
from linksurf.components.base import Component
from linksurf.logger import Logger

EXCHANGE = "linksurf.exchange"


class RabbitMQBroker(Broker):
    def __init__(self, host: str = "localhost", port: int = 5672):
        super().__init__()

        self.host = host
        self.port = port

        self.connection: pika.BlockingConnection | None = None
        self.channel: BlockingChannel | None = None
        self.components: list[Component] = []

    def connect(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self.host, port=self.port)
        )

        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
        self.channel.basic_qos(prefetch_count=1)

    def disconnect(self):
        if self.connection and not self.connection.is_closed:
            self.connection.close()

    def seed(self, topic: str, data: Any):
        self.publish(topic, data, MAX_QUEUE_PRIORITY)

    def subscribe(self, topic: str, handler: Callable[[Payload], None]):
        self.channel.queue_declare(queue=topic, durable=True, arguments={"x-max-priority": MAX_QUEUE_PRIORITY})
        self.channel.queue_bind(exchange=EXCHANGE, queue=topic, routing_key=topic)

        def callback(
                ch: BlockingChannel,
                method: pika.spec.Basic.Deliver,
                _: pika.spec.BasicProperties,
                body: bytes,
        ):
            try:
                data = Payload.from_dict(json.loads(body))
            except Exception as e:
                Logger().error("broker.malformed_message", exception=str(e))

                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

                return

            handler(data)

            ch.basic_ack(delivery_tag=method.delivery_tag)

        self.channel.basic_consume(queue=topic, on_message_callback=callback)

    def publish(self, topic: str, data: Any, priority: int = MIN_QUEUE_PRIORITY):
        self.channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=topic,
            body=json.dumps(data.to_dict()).encode(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                priority=priority,
            ),
        )

    def delayed_publish(self, topic: str, data: Any, delay_seconds: int, priority: int = MIN_QUEUE_PRIORITY):
        delay_queue = f"{topic}.delay.{delay_seconds}"

        self.channel.queue_declare(
            queue=delay_queue,
            durable=True,
            arguments={
                "x-message-ttl": delay_seconds * 1000,
                "x-dead-letter-exchange": EXCHANGE,
                "x-dead-letter-routing-key": topic,
            },
        )

        self.channel.basic_publish(
            exchange="",
            routing_key=delay_queue,
            body=json.dumps(data.to_dict()).encode(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                priority=priority,
            ),
        )

    def loop(self):
        self.channel.start_consuming()

    def stop(self):
        if self.channel is not None:
            self.channel.stop_consuming()
