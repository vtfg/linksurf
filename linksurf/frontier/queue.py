import json
import time

import aio_pika

from linksurf.constants import QUEUE_MAX_PRIORITY, QUEUE_NAME
from linksurf.frontier.cache import get_redis
from linksurf.frontier.filter import is_url_allowed, normalize_url
from linksurf.frontier.robots import Robots
from linksurf.helpers import get_domain_name, get_env, hash_url

_SEEN_KEY = "frontier:seen"
_DOMAIN_DELAY_PREFIX = "frontier:domain:next:"

CRAWL_DELAY = 2

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")


class Queue:
    def __init__(self):
        self.redis = get_redis()
        self.robots = Robots()
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        self._channel = await connection.channel()

        await self._channel.declare_queue(QUEUE_NAME, durable=True, arguments={"x-max-priority": QUEUE_MAX_PRIORITY})

    async def _publish(self, url: str, depth: int) -> None:
        priority = max(0, QUEUE_MAX_PRIORITY - depth)

        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps({"url": url, "depth": depth}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority,
            ),
            routing_key=QUEUE_NAME,
        )

    async def push(self, url: str, depth: int) -> bool:
        url = normalize_url(url)

        if not is_url_allowed(url):
            return False

        if not await self.robots.can_fetch(url):
            return False

        url_hash = hash_url(url)

        if not await self.redis.sadd(_SEEN_KEY, url_hash):
            return False

        await self._publish(url, depth)

        return True

    async def reserve_slot(self, url: str) -> float:
        domain = get_domain_name(url)
        domain_key = f"{_DOMAIN_DELAY_PREFIX}{domain}"

        now = time.time()
        raw = await self.redis.get(domain_key)

        next_at = max(now, float(raw)) if raw else now
        delay = max(0.0, next_at - now)

        await self.redis.set(domain_key, next_at + CRAWL_DELAY)

        return delay

    async def flush(self) -> None:
        await self.redis.delete(_SEEN_KEY)
