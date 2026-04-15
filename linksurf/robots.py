from urllib.robotparser import RobotFileParser

from linksurf.cache import get_redis
from linksurf.fetcher import Fetcher
from linksurf.helpers import get_base_domain, get_domain_name

TTL = 60 * 60 * 24  # 24 hours


class Robots:
    def _build_parser(self, text: str) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse(text.splitlines())

        return parser

    def _fetch(self, domain: str) -> str | None:
        response = Fetcher().fetch(f"{domain}/robots.txt")

        if response.status_code == 200 and "text/plain" in response.headers["Content-Type"].lower():
            return response.text

        return None

    async def _get_parser(self, url: str) -> RobotFileParser:
        domain = get_base_domain(url)
        domain_name = get_domain_name(domain)

        key = f"robots:{domain_name}"

        redis = get_redis()

        cached = await redis.get(key)

        if cached is not None:
            print(f"Using cached robots for {domain}")

            return self._build_parser(cached.decode())

        print(f"Fetching robots for {domain}")

        text = self._fetch(domain) or ""

        if not text:
            print(f"No robots.txt found for {domain}, caching as empty")

        await redis.set(key, text, ex=TTL)

        return self._build_parser(text)

    async def can_fetch(self, url: str) -> bool:
        parser = await self._get_parser(url)

        return parser.can_fetch("*", url)
