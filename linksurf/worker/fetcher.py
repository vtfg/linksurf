from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

from linksurf.helpers import get_env

load_dotenv()

proxy_http = get_env("PROXY_HTTP_URL")
proxy_https = get_env("PROXY_HTTPS_URL")
user_agent = get_env("USER_AGENT")


class Fetcher:
    def fetch(self, url: str) -> requests.Response:
        split = urlsplit(url)

        if split.scheme in ["http", "https"]:
            return self._http(url)
        else:
            raise NotImplementedError()

    def _http(self, url: str) -> requests.Response:
        headers = {
            "User-Agent": user_agent,
        }

        proxies = {
            "http": proxy_http,
            "https": proxy_https,
        }

        return requests.get(url, headers=headers, proxies=proxies, allow_redirects=False)
