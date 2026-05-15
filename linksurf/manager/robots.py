from urllib.robotparser import RobotFileParser

import httpx

from linksurf.helpers import get_base_domain, get_domain_name
from linksurf.manager.cache import get_next_proxy, get_robots, save_robots


class Robots:
    def _build_parser(self, text: str) -> RobotFileParser:
        parser = RobotFileParser()

        parser.parse(text.splitlines())

        return parser

    async def _fetch(self, domain: str) -> str | None:
        proxy = await get_next_proxy()

        mounts = {
            "http://": httpx.AsyncHTTPTransport(proxy=proxy, retries=0),
            "https://": httpx.AsyncHTTPTransport(proxy=proxy, retries=0),
        }

        async with httpx.AsyncClient(mounts=mounts, follow_redirects=False) as client:
            response = await client.get(f"{domain}/robots.txt", timeout=10)

        if response.status_code == 200 and "text/plain" in response.headers.get("content-type", "").lower():
            return response.text

        return None

    async def _get_parser(self, url: str) -> RobotFileParser:
        domain = get_base_domain(url)
        domain_name = get_domain_name(domain)

        cached = await get_robots(domain_name)

        if cached is not None:
            return self._build_parser(cached)

        text = await self._fetch(domain) or ""

        await save_robots(domain_name, text)

        return self._build_parser(text)

    async def can_fetch(self, url: str) -> bool:
        parser = await self._get_parser(url)

        return parser.can_fetch("*", url)
