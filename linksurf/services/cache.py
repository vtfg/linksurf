import logging
from typing import Tuple

import redis

from linksurf.common.models import URL
from linksurf.services.base import Service

logger = logging.getLogger(__name__)

ONE_DAY_IN_SECONDS = 60 * 60 * 24

_DOMAIN_STATUS_CACHE_KEY_PREFIX = "linksurf:domain:"
_DOMAIN_STATUS_CACHE_TTL = ONE_DAY_IN_SECONDS
_URL_SEEN_CACHE_KEY = "linksurf:seen"
_ROBOTS_CACHE_KEY_PREFIX = "linksurf:robots:"
_ROBOTS_CACHE_TTL = ONE_DAY_IN_SECONDS


class Cache(Service):
    NAME = "cache"

    def save_domain_status(self, domain: str, port: int, available: bool, ip: str):
        pass

    def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str]:
        pass

    def save_domain_robots_txt(self, domain: str, contents: str) -> None:
        pass

    def get_domain_robots_txt(self, domain: str) -> str | None:
        pass

    def mark_url_seen(self, url: URL) -> None:
        pass

    def is_url_seen(self, url: URL) -> bool:
        pass


class RedisCache(Cache):
    def __init__(self, host: str, port: int, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._client: redis.Redis | None = None

    def on_start(self):
        self._client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)

        print(f"Connected to Redis at {self.host}:{self.port}/{self.db}")

    def on_stop(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def save_domain_status(self, domain: str, port: int, available: bool, ip: str):
        key = f"{_DOMAIN_STATUS_CACHE_KEY_PREFIX}{domain}@{port}"

        self._client.hset(key, mapping={
            "available": int(available),
            "ip": ip
        })

        self._client.expire(key, _DOMAIN_STATUS_CACHE_TTL)

    def get_domain_status(self, domain: str, port: int) -> Tuple[bool, str] | None:
        key = f"{_DOMAIN_STATUS_CACHE_KEY_PREFIX}{domain}@{port}"

        cached = self._client.hgetall(key)

        if cached:
            available = cached.get("available") == "1"
            ip = cached.get("ip")

            return available, ip

        return None

    def save_domain_robots_txt(self, domain: str, contents: str) -> None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        self._client.set(key, contents, ex=_ROBOTS_CACHE_TTL)

    def get_domain_robots_txt(self, domain: str) -> str | None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        cached = self._client.get(key)

        return cached or None

    def mark_url_seen(self, url: URL) -> None:
        self._client.sadd(_URL_SEEN_CACHE_KEY, url.hash)

    def is_url_seen(self, url: URL) -> bool:
        return self._client.sismember(_URL_SEEN_CACHE_KEY, url.hash) == 1
