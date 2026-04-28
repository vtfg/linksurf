import json
import time
from urllib.parse import urlsplit

import aio_pika

from linksurf.frontier.cache import get_redis
from linksurf.frontier.robots import Robots
from linksurf.helpers import get_domain_name, get_env, hash_url

_SEEN_KEY = "frontier:seen"
_DOMAIN_NEXT_PREFIX = "frontier:domain:next:"

CRAWL_DELAY = 2

RABBITMQ_URL = get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")
QUEUE_NAME = "frontier.urls"

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


class Queue:
    def __init__(self):
        self.redis = get_redis()
        self.robots = Robots()
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def connect(self) -> None:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        self._channel = await connection.channel()

        await self._channel.declare_queue(QUEUE_NAME, durable=True)

    async def _publish(self, url: str, depth: int) -> None:
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps({"url": url, "depth": depth}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=QUEUE_NAME,
        )

    async def seed(self, url: str) -> bool:
        if urlsplit(url).scheme not in ("http", "https"):
            return False

        if _is_blocked(url):
            return False

        await self._publish(url, 0)

        return True

    async def push(self, url: str, depth: int) -> bool:
        if urlsplit(url).scheme not in ("http", "https"):
            return False

        if _is_blocked(url):
            return False

        if not await self.robots.can_fetch(url):
            return False

        url_hash = hash_url(url)

        if await self.redis.sismember(_SEEN_KEY, url_hash):
            return False

        await self._publish(url, depth)

        return True

    async def mark_seen(self, url_hash: str) -> None:
        await self.redis.sadd("frontier:seen", url_hash)

    async def reserve_slot(self, url: str) -> float:
        domain = get_domain_name(url)
        domain_key = f"{_DOMAIN_NEXT_PREFIX}{domain}"

        now = time.time()
        raw = await self.redis.get(domain_key)

        next_at = max(now, float(raw)) if raw else now
        delay = max(0.0, next_at - now)

        await self.redis.set(domain_key, next_at + CRAWL_DELAY)

        return delay

    async def flush(self) -> None:
        await self.redis.delete(_SEEN_KEY)
