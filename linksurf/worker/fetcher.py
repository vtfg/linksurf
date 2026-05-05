from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter

from linksurf.helpers import get_env

USER_AGENT = get_env("USER_AGENT")


class Fetcher:
    def __init__(self):
        self._session = requests.Session()
        adapter = HTTPAdapter(max_retries=0)

        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def fetch(self, url: str, proxy: str) -> requests.Response:
        split = urlsplit(url)

        if split.scheme in ["http", "https"]:
            return self._http(url, proxy)
        else:
            raise NotImplementedError()

    def _http(self, url: str, proxy: str) -> requests.Response:
        headers = {
            "User-Agent": USER_AGENT,
        }

        proxies = {
            "http": proxy,
            "https": proxy,
        }

        response = self._session.get(url, headers=headers, proxies=proxies, allow_redirects=False)

        self._session.cookies.clear()

        return response
