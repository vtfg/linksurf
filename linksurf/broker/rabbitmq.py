import json
from typing import Any, Callable

import pika
import pika.spec
from pika.adapters.blocking_connection import BlockingChannel

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_QUEUE_PRIORITY, MIN_QUEUE_PRIORITY, MAX_RETRIES
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

    def pipeline(self, components: list[Component]):
        self.components = components

        for component in components:
            topic = component.CONSUMES_FROM

            def handler(data: Payload, _component: Component = component, _topic: str = topic):
                if data.retrying:
                    # increment before processing so events reflect the current retry count
                    data.retries += 1

                result = _component.process(data)

                if result.error is not None:
                    error = result.error

                    if error.retriable and data.retries < MAX_RETRIES:
                        data.retrying = True
                        data.priority = max(MIN_QUEUE_PRIORITY, data.priority - 1)

                        if error.delay_seconds:
                            self.delayed_publish(_topic, data, error.delay_seconds)
                        else:
                            self.publish(_topic, data)
                    else:
                        Logger().warning(
                            "broker.discard",
                            url=data.url.address,
                            topic=_topic,
                            retries=data.retries,
                            reason=error.message,
                            retriable=error.retriable,
                        )

                    return

                if result.data is not None:
                    if isinstance(result.data, dict):
                        for next_topic, data in result.data.items():
                            payloads = data if isinstance(data, list) else [data]

                            for payload in payloads:
                                payload.retries = 0
                                payload.retrying = False

                                self.publish(next_topic, payload)
                    else:
                        result.data.retries = 0
                        result.data.retrying = False

                        produces_to = getattr(_component, "PRODUCES_TO", None)

                        if produces_to is not None:
                            if isinstance(produces_to, list):
                                for next_topic in produces_to:
                                    self.publish(next_topic, result.data)
                            else:
                                self.publish(produces_to, result.data)

            self.subscribe(topic, handler)

    def seed(self, topic: str, data: Any):
        self.publish(topic, data)

    def subscribe(self, topic: str, handler: Callable[[Payload], None]):
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

    def delayed_publish(self, topic: str, data: Any, delay_seconds: int):
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
                priority=getattr(data, "priority", 0),
            ),
        )

    def loop(self):
        self.channel.start_consuming()

    def stop(self):
        if self.channel is not None:
            self.channel.stop_consuming()
