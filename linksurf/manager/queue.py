import json

import aio_pika

from linksurf.constants import EXCHANGE_NAME
from linksurf.helpers import get_domain_name, get_env, hash_url
from linksurf.manager.cache import mark_url_as_seen
from linksurf.manager.filter import is_url_allowed, normalize_url
from linksurf.manager.prioritizer import Prioritizer
from linksurf.manager.robots import Robots

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")


class Queue:
    def __init__(self):
        self.robots = Robots()
        self.prioritizer = Prioritizer()
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        self._channel = await connection.channel()

        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            type="x-consistent-hash",
            durable=True,
        )

    async def _publish(self, url: str, depth: int) -> None:
        priority = await self.prioritizer.score(url)
        domain = get_domain_name(url)

        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps({"url": url, "depth": depth}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority,
            ),
            routing_key=domain,
        )

    async def push(self, url: str, depth: int) -> bool:
        url = normalize_url(url)

        if not is_url_allowed(url):
            return False

        if not await self.robots.can_fetch(url):
            return False

        url_hash = hash_url(url)

        if not await mark_url_as_seen(url_hash):
            return False

        await self._publish(url, depth)

        return True
