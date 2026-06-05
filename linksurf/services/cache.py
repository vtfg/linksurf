import logging

import redis

from linksurf.common.models import URL
from linksurf.services.base import Service

logger = logging.getLogger(__name__)

_URL_SEEN_CACHE_KEY = "linksurf:seen"


class Cache(Service):
    NAME = "cache"

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

    def mark_url_seen(self, url: URL) -> None:
        self._client.sadd(_URL_SEEN_CACHE_KEY, url.hash)

    def is_url_seen(self, url: URL) -> bool:
        return self._client.sismember(_URL_SEEN_CACHE_KEY, url.hash) == 1
