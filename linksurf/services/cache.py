import math
from dataclasses import dataclass
from typing import Tuple

import redis.asyncio as redis

from linksurf.common.models import URL
from linksurf.common.settings import Settings
from linksurf.services.base import Service

ONE_DAY_IN_SECONDS = 60 * 60 * 24

_DOMAIN_KEY_PREFIX = "linksurf:domain:"
_DOMAIN_STATUS_SUFFIX = ":status"
_DOMAIN_METRICS_SUFFIX = ":metrics"
_DOMAIN_ROBOTS_SUFFIX = ":robots"
_DOMAIN_STATUS_TTL = ONE_DAY_IN_SECONDS
_URL_SEEN_CACHE_KEY = "linksurf:seen"
_ROBOTS_CACHE_TTL = ONE_DAY_IN_SECONDS
_RELEASE_TIME_KEY_PREFIX = "linksurf:release:"


@dataclass
class DomainMetrics:
    total_crawled: int
    avg_response_ms: float
    avg_content_size: float


@dataclass
class RobotsRecord:
    status_code: int
    content_type: str | None
    text: str


class Cache(Service):
    NAME = "cache"

    async def save_domain_status(self, domain: str, port: int, available: bool, ip: str) -> None:
        raise NotImplementedError()

    async def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str] | None:
        raise NotImplementedError()

    async def save_domain_robots_txt(self, domain: str, port: int, status_code: int, content_type: str | None,
                                     text: str) -> None:
        raise NotImplementedError()

    async def get_domain_robots_txt(self, domain: str, port: int) -> RobotsRecord | None:
        raise NotImplementedError()

    async def mark_url_seen(self, url: URL) -> None:
        raise NotImplementedError()

    async def unmark_url_seen(self, url: URL) -> None:
        raise NotImplementedError()

    async def is_url_seen(self, url: URL) -> bool:
        raise NotImplementedError()

    async def save_domain_release_time(self, domain: str, port: int, time: float) -> None:
        raise NotImplementedError()

    async def get_domain_release_time(self, domain: str, port: int) -> float | None:
        raise NotImplementedError()

    async def get_domain_metrics(self, domain: str, port: int) -> DomainMetrics | None:
        raise NotImplementedError()

    async def update_domain_metrics(self, domain: str, port: int, response_ms: float, content_size: int) -> None:
        raise NotImplementedError()


class RedisCache(Cache):
    def __init__(self, host: str, port: int, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._client: redis.Redis | None = None

    async def on_start(self, settings: Settings):
        client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)

        await client.ping()

        self._client = client

    async def on_stop(self):
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def save_domain_status(self, domain: str, port: int, available: bool, ip: str) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_STATUS_SUFFIX}"

        await self._client.hset(key, mapping={"available": int(available), "ip": ip})
        await self._client.expire(key, _DOMAIN_STATUS_TTL)

    async def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str] | None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_STATUS_SUFFIX}"

        cached = await self._client.hgetall(key)

        if cached:
            return cached.get("available") == "1", cached.get("ip")

        return None

    async def save_domain_robots_txt(self, domain: str, port: int, status_code: int, content_type: str | None,
                                     text: str) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_ROBOTS_SUFFIX}"

        await self._client.hset(key, mapping={
            "status_code": status_code,
            "content_type": content_type or "",
            "text": text,
        })

        await self._client.expire(key, _ROBOTS_CACHE_TTL)

    async def get_domain_robots_txt(self, domain: str, port: int) -> RobotsRecord | None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_ROBOTS_SUFFIX}"

        data = await self._client.hgetall(key)

        if not data:
            return None

        return RobotsRecord(
            status_code=int(data["status_code"]),
            content_type=data.get("content_type"),
            text=data.get("text", ""),
        )

    async def mark_url_seen(self, url: URL) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        await self._client.sadd(_URL_SEEN_CACHE_KEY, url.hash)

    async def unmark_url_seen(self, url: URL) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        await self._client.srem(_URL_SEEN_CACHE_KEY, url.hash)

    async def is_url_seen(self, url: URL) -> bool:
        if self._client is None:
            raise RuntimeError("Service not started.")

        return await self._client.sismember(_URL_SEEN_CACHE_KEY, url.hash) == 1

    async def save_domain_release_time(self, domain: str, port: int, time: float) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_RELEASE_TIME_KEY_PREFIX}{domain}@{port}"

        await self._client.set(key, time, ex=math.ceil(time))

    async def get_domain_release_time(self, domain: str, port: int) -> float | None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_RELEASE_TIME_KEY_PREFIX}{domain}@{port}"

        value = await self._client.get(key)

        return float(value) if value is not None else None

    async def get_domain_metrics(self, domain: str, port: int) -> DomainMetrics | None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_METRICS_SUFFIX}"

        data = await self._client.hgetall(key)

        if not data:
            return None

        return DomainMetrics(
            total_crawled=int(data["total_crawled"]),
            avg_response_ms=float(data["avg_response_ms"]),
            avg_content_size=float(data["avg_content_size"]),
        )

    async def update_domain_metrics(self, domain: str, port: int, response_ms: float, content_size: int) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_METRICS_SUFFIX}"

        current = await self.get_domain_metrics(domain, port)

        if current is None:
            total = 1
            avg_response_ms = response_ms
            avg_content_size = float(content_size)
        else:
            total = current.total_crawled + 1
            avg_response_ms = current.avg_response_ms + (response_ms - current.avg_response_ms) / total
            avg_content_size = current.avg_content_size + (content_size - current.avg_content_size) / total

        await self._client.hset(key, mapping={
            "total_crawled": total,
            "avg_response_ms": avg_response_ms,
            "avg_content_size": avg_content_size,
        })
