import asyncio
import hashlib
import json

import redis.asyncio as aioredis

from linksurf.database import URL

_QUEUE_KEY = "frontier:queue"
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

        payload = json.dumps({"address": url.address, "depth": url.depth})

        await self._redis.zadd(_QUEUE_KEY, {payload: url.depth})

        return True

    async def pop(self) -> URL | None:
        result = await self._redis.zpopmin(_QUEUE_KEY, count=1)

        if not result:
            return None

        payload, _ = result[0]
        data = json.loads(payload)

        return URL(address=data["address"], depth=data["depth"])

    async def empty(self) -> bool:
        return await self._redis.zcard(_QUEUE_KEY) == 0

    async def size(self) -> int:
        return await self._redis.zcard(_QUEUE_KEY)

    async def wait_for_domain(self, domain: str) -> None:
        key = f"{_DOMAIN_KEY_PREFIX}{domain}"

        ttl = await self._redis.pttl(key)

        if ttl > 0:
            await asyncio.sleep(ttl / 1000)

    async def mark_domain_crawled(self, domain: str) -> None:
        await self._redis.set(f"{_DOMAIN_KEY_PREFIX}{domain}", 1, ex=CRAWL_DELAY)
