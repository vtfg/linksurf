import asyncio
from urllib.robotparser import RobotFileParser

import requests

from linksurf.frontier.cache import get_redis
from linksurf.helpers import get_base_domain, get_domain_name

TTL = 60 * 60 * 24  # 24 hours


class Robots:
    def _build_parser(self, text: str) -> RobotFileParser:
        parser = RobotFileParser()

        parser.parse(text.splitlines())

        return parser

    async def _fetch(self, domain: str) -> str | None:
        response = await asyncio.to_thread(
            requests.get, f"{domain}/robots.txt", allow_redirects=False
        )

        if response.status_code == 200 and "text/plain" in response.headers.get("Content-Type", "").lower():
            return response.text

        return None

    async def _get_parser(self, url: str) -> RobotFileParser:
        domain = get_base_domain(url)
        domain_name = get_domain_name(domain)
        key = f"robots:{domain_name}"

        redis = get_redis()

        cached = await redis.get(key)

        if cached is not None:
            return self._build_parser(cached.decode())

        text = await self._fetch(domain) or ""

        await redis.set(key, text, ex=TTL)

        return self._build_parser(text)

    async def can_fetch(self, url: str) -> bool:
        parser = await self._get_parser(url)

        return parser.can_fetch("*", url)
