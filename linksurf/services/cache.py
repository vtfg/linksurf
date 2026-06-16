from dataclasses import dataclass
from typing import Tuple

import redis

from linksurf.common.models import URL
from linksurf.common.settings import Settings
from linksurf.services.base import Service

ONE_DAY_IN_SECONDS = 60 * 60 * 24

_DOMAIN_KEY_PREFIX = "linksurf:domain:"
_DOMAIN_STATUS_SUFFIX = ":status"
_DOMAIN_METRICS_SUFFIX = ":metrics"
_DOMAIN_STATUS_TTL = ONE_DAY_IN_SECONDS
_URL_SEEN_CACHE_KEY = "linksurf:seen"
_ROBOTS_CACHE_KEY_PREFIX = "linksurf:robots:"
_ROBOTS_CACHE_TTL = ONE_DAY_IN_SECONDS
_LAST_FETCH_KEY_PREFIX = "linksurf:fetch:"
_LAST_FETCH_TTL = ONE_DAY_IN_SECONDS


@dataclass
class DomainMetrics:
    total_crawled: int
    avg_response_ms: float
    avg_content_size: float


class Cache(Service):
    NAME = "cache"

    def save_domain_status(self, domain: str, port: int, available: bool, ip: str) -> None:
        pass

    def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str] | None:
        pass

    def save_domain_robots_txt(self, domain: str, contents: str) -> None:
        pass

    def get_domain_robots_txt(self, domain: str) -> str | None:
        pass

    def mark_url_seen(self, url: URL) -> None:
        pass

    def is_url_seen(self, url: URL) -> bool:
        pass

    def save_domain_last_fetch(self, domain: str, port: int, timestamp: float) -> None:
        pass

    def get_domain_last_fetch(self, domain: str, port: int) -> float | None:
        pass

    def get_domain_metrics(self, domain: str, port: int) -> DomainMetrics | None:
        pass

    def update_domain_metrics(self, domain: str, port: int, response_ms: float, content_size: int) -> None:
        pass


class RedisCache(Cache):
    def __init__(self, host: str, port: int, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._client: redis.Redis | None = None

    def on_start(self, settings: Settings):
        self._client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)

        self._client.ping()

    def on_stop(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def save_domain_status(self, domain: str, port: int, available: bool, ip: str) -> None:
        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_STATUS_SUFFIX}"

        self._client.hset(key, mapping={"available": int(available), "ip": ip})
        self._client.expire(key, _DOMAIN_STATUS_TTL)

    def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str] | None:
        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_STATUS_SUFFIX}"

        cached = self._client.hgetall(key)

        if cached:
            return cached.get("available") == "1", cached.get("ip")

        return None

    def save_domain_robots_txt(self, domain: str, contents: str) -> None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        self._client.set(key, contents, ex=_ROBOTS_CACHE_TTL)

    def get_domain_robots_txt(self, domain: str) -> str | None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        return self._client.get(key) or None

    def mark_url_seen(self, url: URL) -> None:
        self._client.sadd(_URL_SEEN_CACHE_KEY, url.hash)

    def is_url_seen(self, url: URL) -> bool:
        return self._client.sismember(_URL_SEEN_CACHE_KEY, url.hash) == 1

    def save_domain_last_fetch(self, domain: str, port: int, timestamp: float) -> None:
        key = f"{_LAST_FETCH_KEY_PREFIX}{domain}@{port}"

        self._client.set(key, timestamp, ex=_LAST_FETCH_TTL)

    def get_domain_last_fetch(self, domain: str, port: int) -> float | None:
        key = f"{_LAST_FETCH_KEY_PREFIX}{domain}@{port}"

        value = self._client.get(key)

        return float(value) if value is not None else None

    def get_domain_metrics(self, domain: str, port: int) -> DomainMetrics | None:
        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_METRICS_SUFFIX}"

        data = self._client.hgetall(key)

        if not data:
            return None

        return DomainMetrics(
            total_crawled=int(data["total_crawled"]),
            avg_response_ms=float(data["avg_response_ms"]),
            avg_content_size=float(data["avg_content_size"]),
        )

    def update_domain_metrics(self, domain: str, port: int, response_ms: float, content_size: int) -> None:
        key = f"{_DOMAIN_KEY_PREFIX}{domain}@{port}{_DOMAIN_METRICS_SUFFIX}"

        current = self.get_domain_metrics(domain, port)

        if current is None:
            total = 1
            avg_response_ms = response_ms
            avg_content_size = float(content_size)
        else:
            total = current.total_crawled + 1
            avg_response_ms = current.avg_response_ms + (response_ms - current.avg_response_ms) / total
            avg_content_size = current.avg_content_size + (content_size - current.avg_content_size) / total

        self._client.hset(key, mapping={
            "total_crawled": total,
            "avg_response_ms": avg_response_ms,
            "avg_content_size": avg_content_size,
        })
