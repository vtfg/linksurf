import asyncio
import hashlib

import redis.asyncio as aioredis

from linksurf.database import URL

_SEEN_KEY = "frontier:seen"
_DOMAIN_KEY_PREFIX = "frontier:domain:"

CRAWL_DELAY = 2  # seconds between requests to the same domain


class URLFrontier:
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def push(self, url: URL) -> bool:
        url_hash = hashlib.sha256(url.address.encode()).hexdigest()

        added = await self._redis.sadd(_SEEN_KEY, url_hash)

        if not added:
            return False

        from linksurf.tasks import crawl_task

        await asyncio.to_thread(crawl_task.delay, url.address, url.depth)

        return True

    async def acquire_domain_slot(self, domain: str) -> None:
        # blocks execution until domain is available
        key = f"{_DOMAIN_KEY_PREFIX}{domain}"

        while True:
            acquired = await self._redis.set(key, 1, nx=True, ex=CRAWL_DELAY)

            if acquired:
                return

            ttl = await self._redis.pttl(key)

            await asyncio.sleep(ttl / 1000 if ttl > 0 else 0.1)

    async def flush(self) -> None:
        await self._redis.delete(_SEEN_KEY)
