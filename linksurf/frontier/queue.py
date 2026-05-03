import json
import time
from datetime import datetime

import aio_pika

from linksurf.constants import QUEUE_MAX_PRIORITY, QUEUE_NAME, DOMAIN_CACHE_KEY_PREFIX
from linksurf.frontier.cache import get_domain_stats, update_domain_last_crawled_at, mark_url_as_seen
from linksurf.frontier.filter import is_url_allowed, normalize_url
from linksurf.frontier.prioritizer import Prioritizer
from linksurf.frontier.robots import Robots
from linksurf.helpers import get_domain_name, get_env, hash_url

CRAWL_DELAY = 2

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")


class Queue:
    def __init__(self):
        self.robots = Robots()
        self.prioritizer = Prioritizer()
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        self._channel = await connection.channel()

        await self._channel.declare_queue(QUEUE_NAME, durable=True, arguments={"x-max-priority": QUEUE_MAX_PRIORITY})

    async def _publish(self, url: str, depth: int) -> None:
        priority = await self.prioritizer.score(url)

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

        if not await mark_url_as_seen(url_hash):
            return False

        await self._publish(url, depth)

        return True

    async def reserve_slot(self, url: str) -> float:
        domain = get_domain_name(url)

        domain_key = f"{DOMAIN_CACHE_KEY_PREFIX}:{domain}"

        stats = await get_domain_stats(domain)

        last_crawled_at = stats.get("total_crawled_urls", 0)

        if last_crawled_at:
            last_crawled_at = datetime.fromisoformat(last_crawled_at.decode()).timestamp()
            next_at = last_crawled_at + CRAWL_DELAY
            delay = max(0.0, next_at - time.time())
        else:
            delay = 0.0

        await update_domain_last_crawled_at(domain_key)

        return delay
