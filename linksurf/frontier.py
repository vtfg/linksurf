import asyncio
import hashlib

import redis.asyncio as aioredis

from linksurf.database import URL
from linksurf.helpers import get_domain_name

_SEEN_KEY = "frontier:seen"
_DOMAIN_KEY_PREFIX = "frontier:domain:"

CRAWL_DELAY = 2  # seconds between requests to the same domain

_BLOCKED_DOMAINS = {
    # Google
    "google.com", "googleapis.com", "googletagmanager.com", "gstatic.com",
    "googleusercontent.com", "youtube.com", "youtu.be", "gmail.com",
    # Meta
    "facebook.com", "instagram.com", "whatsapp.com", "meta.com", "fb.com", "fbcdn.net",
    # Apple
    "apple.com", "icloud.com",
    # Amazon
    "amazon.com", "amazonaws.com", "aws.amazon.com",
    # Microsoft
    "microsoft.com", "live.com", "outlook.com", "hotmail.com", "bing.com", "msn.com",
    # Netflix
    "netflix.com",
    # X / Twitter
    "twitter.com", "x.com", "t.co",
    # LinkedIn
    "linkedin.com",
    # TikTok
    "tiktok.com",
    # Snapchat
    "snapchat.com",
    # Pinterest
    "pinterest.com",
    # Reddit
    "reddit.com",
    # Spotify
    "spotify.com",
    # Adobe
    "adobe.com",
    # Salesforce
    "salesforce.com",
    # PayPal
    "paypal.com",
    # Cloudflare
    "cloudflare.com",
    # Shopify
    "shopify.com",
    # WordPress
    "wordpress.com", "wp.com",
    # Tracking / analytics
    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
}


def _is_blocked(url: str) -> bool:
    netloc = get_domain_name(url)
    return any(netloc == d or netloc.endswith(f".{d}") for d in _BLOCKED_DOMAINS)


class URLFrontier:
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def push(self, url: URL) -> bool:
        if _is_blocked(url.address):
            return False

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
