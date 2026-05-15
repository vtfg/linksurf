from urllib.parse import urlsplit

import httpx

from linksurf.helpers import get_env

USER_AGENT = get_env("USER_AGENT")


class Fetcher:
    async def fetch(self, url: str, proxy: str) -> httpx.Response:
        split = urlsplit(url)

        if split.scheme in ["http", "https"]:
            return await self._http(url, proxy)
        else:
            raise NotImplementedError()

    async def _http(self, url: str, proxy: str) -> httpx.Response:
        mounts = {
            "http://": httpx.AsyncHTTPTransport(proxy=proxy, retries=0),
            "https://": httpx.AsyncHTTPTransport(proxy=proxy, retries=0),
        }

        async with httpx.AsyncClient(mounts=mounts, follow_redirects=False) as client:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})

        return response
