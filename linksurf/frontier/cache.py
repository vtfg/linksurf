import redis.asyncio as aioredis

from linksurf.helpers import get_env

REDIS_URL = get_env("REDIS_URL", default="redis://localhost:6379")

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis

    _redis = aioredis.from_url(REDIS_URL)


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected.")

    return _redis
