import asyncio
import json
from typing import Any, Callable, Awaitable

import aio_pika

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_QUEUE_PRIORITY, MIN_QUEUE_PRIORITY
from linksurf.common.payload import Payload
from linksurf.logger import Logger

EXCHANGE = "linksurf.exchange"


class RabbitMQBroker(Broker):
    connection: aio_pika.abc.AbstractRobustConnection
    channel: aio_pika.abc.AbstractRobustChannel

    def __init__(self, host: str = "localhost", port: int = 5672):
        super().__init__()

        self.host = host
        self.port = port

        self._consumers: list[tuple[aio_pika.abc.AbstractQueue, str]] = []
        self._in_flight: set[asyncio.Task] = set()

    async def connect(self):
        self.connection = await aio_pika.connect_robust(
            host=self.host,
            port=self.port
        )

        self.channel = await self.connection.channel()
        await self.channel.declare_exchange(name=EXCHANGE, type="direct", durable=True)
        await self.channel.set_qos(prefetch_count=1)

        self._stop_event = asyncio.Event()

    async def disconnect(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()

    async def seed(self, topic: str, data: Any):
        await self.publish(topic, data, MAX_QUEUE_PRIORITY)

    async def subscribe(self, topic: str, handler: Callable[[Payload], Awaitable[None]], concurrency: int = 1):
        if concurrency < 1:
            raise ValueError("Concurrency must be >= 1.")

        queue = await self.channel.declare_queue(name=topic, durable=True,
                                                 arguments={"x-max-priority": MAX_QUEUE_PRIORITY})
        await queue.bind(exchange=EXCHANGE, routing_key=topic)

        async def callback(message: aio_pika.abc.AbstractIncomingMessage):
            task = asyncio.current_task()
            self._in_flight.add(task)

            try:
                async with message.process(ignore_processed=True):
                    try:
                        data = Payload.from_dict(json.loads(message.body))
                    except Exception as e:
                        Logger().error("broker.malformed_message", exception=str(e))

                        await message.reject(requeue=False)

                        return

                    await handler(data)
            finally:
                self._in_flight.discard(task)

        consumer_tag = await queue.consume(callback)
        self._consumers.append((queue, consumer_tag))

    async def publish(self, topic: str, data: Any, priority: int = MIN_QUEUE_PRIORITY):
        exchange = await self.channel.get_exchange(EXCHANGE)

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(data.to_dict()).encode(),
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority,
            ),
            routing_key=topic,
        )

    async def delayed_publish(self, topic: str, data: Any, delay_seconds: int, priority: int = MIN_QUEUE_PRIORITY):
        delay_queue = f"{topic}.delay.{delay_seconds}"

        queue = await self.channel.declare_queue(
            name=delay_queue,
            durable=True,
            arguments={
                "x-message-ttl": delay_seconds * 1000,
                "x-dead-letter-exchange": EXCHANGE,
                "x-dead-letter-routing-key": topic,
            },
        )

        exchange = await self.channel.get_exchange(EXCHANGE)

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(data.to_dict()).encode(),
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority,
            ),
            routing_key=delay_queue,
        )

    async def loop(self):
        # every queue is already being consumed at this point (subscribe() was called
        # once per component before this); this just blocks the coroutine open
        await self._stop_event.wait()

        # stop accepting new messages before disconnect() runs, then let whatever's
        # already in flight finish naturally instead of being cancelled mid-request
        for queue, consumer_tag in self._consumers:
            await queue.cancel(consumer_tag)

        if self._in_flight:
            Logger().info("broker.draining", pending=len(self._in_flight))

            await asyncio.gather(*self._in_flight, return_exceptions=True)

    def stop(self):
        if self._stop_event is not None:
            self._stop_event.set()
