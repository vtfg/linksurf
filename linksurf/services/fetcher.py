from urllib.parse import urlsplit

from requests import Session

from linksurf.common.models import HTTPRequest, HTTPResponse
from linksurf.services.base import Service


class Fetcher(Service):
    NAME = "fetcher"

    def http(self, request: HTTPRequest) -> HTTPResponse:
        pass


class RequestsFetcher(Fetcher):
    def __init__(self):
        self._session: Session | None = None

    def on_start(self):
        self._session = Session()

    def on_stop(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    def http(self, request: HTTPRequest) -> HTTPResponse:
        scheme = urlsplit(request.url).scheme

        if scheme not in ["http", "https"]:
            raise ValueError(f"Unsupported scheme: {scheme}")

        proxies = None

        if request.proxy:
            proxies = {"http": request.proxy, "https": request.proxy}

        response = self._session.request(
            method=request.method,
            url=request.url,
            proxies=proxies,
            timeout=request.timeout,
            allow_redirects=request.follow_redirects,
        )

        self._session.cookies.clear()

        elapsed_ms = response.elapsed.total_seconds() * 1000

        return HTTPResponse(
            url=response.url,
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            encoding=response.encoding,
            elapsed_ms=elapsed_ms,
            redirects=[r.url for r in response.history],
            request=request,
        )
