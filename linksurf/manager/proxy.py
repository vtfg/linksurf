import asyncio

import httpx

from linksurf.manager.cache import get_next_proxy, seed_proxy_pool

_HTTPBIN_URL = "http://httpbin.org/ip"


class ProxyPool:
    async def setup(self, proxy_urls: list[str]) -> None:
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(*[self._validate(client, url) for url in proxy_urls])

        valid = [url for url, ok in zip(proxy_urls, results) if ok]

        if not valid:
            raise RuntimeError("No valid proxies available")

        await seed_proxy_pool(valid)

        print(f"Proxy pool ready: {len(valid)}/{len(proxy_urls)} proxies available")

    async def _validate(self, client: httpx.AsyncClient, proxy_url: str) -> bool:
        try:
            async with httpx.AsyncClient(proxy=proxy_url) as proxied:
                response = await proxied.get(_HTTPBIN_URL, timeout=10)

            return response.status_code == 200
        except Exception as e:
            print(f"Proxy failed: {proxy_url} — {e}")

            return False

    async def get_next(self) -> str:
        return await get_next_proxy()
