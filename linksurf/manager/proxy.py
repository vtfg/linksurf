import asyncio

import requests

from linksurf.manager.cache import get_next_proxy, seed_proxy_pool

_HTTPBIN_URL = "http://httpbin.org/ip"


class ProxyPool:
    async def setup(self, proxy_urls: list[str]) -> None:
        results = await asyncio.gather(*[self._validate(url) for url in proxy_urls])

        valid = []

        for url, ok in zip(proxy_urls, results):
            if ok:
                valid.append(url)

        if not valid:
            raise RuntimeError("No valid proxies available")

        await seed_proxy_pool(valid)

        print(f"Proxy pool ready: {len(valid)}/{len(proxy_urls)} proxies available")

    async def _validate(self, proxy_url: str) -> bool:
        try:
            response = await asyncio.to_thread(
                requests.get,
                _HTTPBIN_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=10,
            )

            ok = response.status_code == 200

            return ok
        except Exception as e:
            print(f"Proxy failed: {proxy_url} — {e}")

            return False

    async def get_next(self) -> str:
        return await get_next_proxy()
