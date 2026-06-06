import logging

import redis

from linksurf.common.models import URL
from linksurf.services.base import Service

logger = logging.getLogger(__name__)

_URL_SEEN_CACHE_KEY = "linksurf:seen"
_ROBOTS_CACHE_KEY_PREFIX = "linksurf:robots:"
_ROBOTS_CACHE_TTL = 60 * 60 * 24  # 24 hours


class Cache(Service):
    NAME = "cache"

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
        self._client = redis.Redis(host=self.host, port=self.port, db=self.db)

        print(f"Connected to Redis at {self.host}:{self.port}/{self.db}")

    def on_stop(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def save_domain_robots_txt(self, domain: str, contents: str) -> None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        self._client.set(key, contents, ex=_ROBOTS_CACHE_TTL)

    def get_domain_robots_txt(self, domain: str) -> str | None:
        key = f"{_ROBOTS_CACHE_KEY_PREFIX}{domain}"

        cached = self._client.get(key)

        return cached.decode() if cached else None

    def mark_url_seen(self, url: URL) -> None:
        self._client.sadd(_URL_SEEN_CACHE_KEY, url.hash)

    def is_url_seen(self, url: URL) -> bool:
        return self._client.sismember(_URL_SEEN_CACHE_KEY, url.hash) == 1
