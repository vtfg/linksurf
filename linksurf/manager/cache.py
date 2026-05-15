from datetime import datetime

import redis.asyncio as aioredis

from linksurf.constants import ROBOTS_TTL
from linksurf.helpers import get_domain_name, get_env, get_root_domain

REDIS_URL = get_env("REDIS_URL", default="redis://localhost:6379")

DOMAIN_CACHE_KEY_PREFIX = "manager:domain:"
ROBOTS_CACHE_KEY_PREFIX = "robots:"
URL_SEEN_CACHE_KEY = "manager:seen"
PROXY_POOL_KEY = "proxy:pool"

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis

    _redis = aioredis.from_url(REDIS_URL)


async def get_robots(domain: str) -> str | None:
    key = f"{ROBOTS_CACHE_KEY_PREFIX}{domain}"

    cached = await _redis.get(key)

    return cached.decode() if cached else None


async def save_robots(domain: str, text: str) -> None:
    key = f"{ROBOTS_CACHE_KEY_PREFIX}{domain}"

    await _redis.set(key, text, ex=ROBOTS_TTL)


async def get_domain_stats(domain: str) -> dict[str, str]:
    raw = await _redis.hgetall(f"{DOMAIN_CACHE_KEY_PREFIX}{domain}")

    return {k.decode(): v.decode() for k, v in raw.items()}


async def update_domain_stats(address: str, response_time: int, size: int, crawled_at: datetime) -> None:
    domain = get_domain_name(address)
    root_domain = get_root_domain(address)

    key = f"{DOMAIN_CACHE_KEY_PREFIX}{domain}"
    root_key = f"{DOMAIN_CACHE_KEY_PREFIX}{root_domain}"

    data = await get_domain_stats(domain)

    total = int(data.get("total_crawled_urls", 0))
    old_avg_response = float(data.get("avg_response_time", 0))
    old_avg_size = float(data.get("avg_page_size", 0))

    new_total = total + 1
    new_avg_response = (old_avg_response * total + response_time) / new_total
    new_avg_size = (old_avg_size * total + size) / new_total

    await _redis.hset(key, mapping={
        "last_crawled_at": crawled_at.isoformat(),
        "avg_response_time": new_avg_response,
        "avg_page_size": new_avg_size,
        "total_crawled_urls": new_total,
    })

    await _redis.hincrby(root_key, "total_crawled_urls", 1)


async def mark_url_as_seen(url_hash: str) -> bool:
    added = await _redis.sadd(URL_SEEN_CACHE_KEY, url_hash)

    return added > 0


async def seed_proxy_pool(proxy_urls: list[str]) -> None:
    await _redis.delete(PROXY_POOL_KEY)
    await _redis.rpush(PROXY_POOL_KEY, *proxy_urls)


async def get_next_proxy() -> str:
    proxy = await _redis.lmove(PROXY_POOL_KEY, PROXY_POOL_KEY, "LEFT", "RIGHT")

    if proxy is None:
        raise RuntimeError("Proxy pool is empty")

    return proxy.decode()
