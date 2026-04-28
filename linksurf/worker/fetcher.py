from urllib.parse import urlsplit

import requests

from linksurf.helpers import get_env

PROXY_HTTP = get_env("PROXY_HTTP_URL")
PROXY_HTTPS = get_env("PROXY_HTTPS_URL")
USER_AGENT = get_env("USER_AGENT")


class Fetcher:
    def fetch(self, url: str) -> requests.Response:
        split = urlsplit(url)

        if split.scheme in ["http", "https"]:
            return self._http(url)
        else:
            raise NotImplementedError()

    def _http(self, url: str) -> requests.Response:
        headers = {
            "User-Agent": USER_AGENT,
        }

        proxies = {
            "http": PROXY_HTTP,
            "https": PROXY_HTTPS,
        }

        return requests.get(url, headers=headers, proxies=proxies, allow_redirects=False)
