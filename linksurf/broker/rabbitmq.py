import json
from typing import Any, Callable

import pika
import pika.spec
from pika.adapters.blocking_connection import BlockingChannel

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_QUEUE_PRIORITY
from linksurf.common.payload import Payload
from linksurf.components.base import Component

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

    def pipeline(self, components: list[Component]):
        self.components = components

        for component in components:
            def handler(data: Any, _component: Component = component):
                result = _component.process(data)

                if result is None or result.error is not None or result.data is None:
                    # Redeliver retriable errors

                    return

                if isinstance(result.data, dict):
                    for topic, payloads in result.data.items():
                        items = payloads if isinstance(payloads, list) else [payloads]
                        for payload in items:
                            self.publish(topic, payload)

                    return

                produces_to = getattr(_component, "PRODUCES_TO", None)

                if produces_to is None:
                    return

                if isinstance(produces_to, list):
                    for topic in produces_to:
                        self.publish(topic, result.data)
                else:
                    self.publish(produces_to, result.data)

            self.subscribe(component.CONSUMES_FROM, handler)

    def seed(self, topic: str, data: Any):
        self.publish(topic, data)

    def subscribe(self, topic: str, handler: Callable[[Any], Any]):
        self.channel.queue_declare(queue=topic, durable=True, arguments={"x-max-priority": MAX_QUEUE_PRIORITY})
        self.channel.queue_bind(exchange=EXCHANGE, queue=topic, routing_key=topic)

        def callback(
                ch: BlockingChannel,
                method: pika.spec.Basic.Deliver,
                _: pika.spec.BasicProperties,
                body: bytes,
        ):
            data = Payload.from_dict(json.loads(body))

            handler(data)

            ch.basic_ack(delivery_tag=method.delivery_tag)

        self.channel.basic_consume(queue=topic, on_message_callback=callback)

    def publish(self, topic: str, data: Any):
        self.channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=topic,
            body=json.dumps(data.to_dict()).encode(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                priority=getattr(data, "priority", 0),
            ),
        )

    def loop(self):
        self.channel.start_consuming()

    def stop(self):
        if self.channel is not None:
            self.channel.stop_consuming()
