from urllib.parse import urlsplit

from httpx import AsyncClient, TooManyRedirects

from linksurf.common.constants import DEFAULT_USER_AGENT, MAX_REDIRECT_DEPTH
from linksurf.common.models import HTTPRequest, HTTPResponse, Redirect
from linksurf.common.settings import Settings
from linksurf.logger import Logger
from linksurf.services.base import Service


class MaxRedirectsError(Exception):
    pass


class Fetcher(Service):
    NAME = "fetcher"

    async def http(self, request: HTTPRequest) -> HTTPResponse:
        raise NotImplementedError()


class HTTPXFetcher(Fetcher):
    def __init__(self):
        self.user_agent = DEFAULT_USER_AGENT
        self.proxy: str | None = None
        self._client: AsyncClient | None = None

    async def on_start(self, settings: Settings):
        self.user_agent = settings.user_agent
        self.proxy = settings.proxy

        client = AsyncClient(proxy=self.proxy)
        client.max_redirects = MAX_REDIRECT_DEPTH

        Logger().debug("service.debug", service="Fetcher", message="Using proxy", proxy=self.proxy)

        self._client = client

    async def on_stop(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def http(self, request: HTTPRequest) -> HTTPResponse:
        if self._client is None:
            raise RuntimeError("Service not started.")

        scheme = urlsplit(request.url).scheme

        if scheme not in ["http", "https"]:
            raise ValueError(f"Unsupported scheme: {scheme}")

        proxy = self.proxy

        if proxy:
            request.proxy = proxy

        request.user_agent = self.user_agent

        headers = {
            "User-Agent": self.user_agent,
        }

        try:
            response = await self._client.request(
                method=request.method,
                url=request.url,
                headers=headers,
                timeout=request.timeout,
                follow_redirects=request.follow_redirects,
            )
        except TooManyRedirects as e:
            raise MaxRedirectsError(str(e)) from e

        self._client.cookies.clear()

        elapsed_ms = response.elapsed.total_seconds() * 1000

        return HTTPResponse(
            url=str(response.url),
            status_code=response.status_code,
            headers=response.headers,
            body=response.content,
            encoding=response.encoding,
            elapsed_ms=elapsed_ms,
            redirects=[
                Redirect(source=str(r.url), target=str(dest.url), status_code=r.status_code, depth=i)
                for i, (r, dest) in enumerate(zip(response.history, response.history[1:] + [response]))
            ],
            request=request,
        )
