import redis.asyncio as aioredis

from linksurf.helpers import get_env

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = aioredis.from_url(get_env("REDIS_URL", default="redis://localhost:6379"))


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis
