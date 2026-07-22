import time
from urllib.parse import urlsplit

from httpx import (
    AsyncClient,
    ConnectTimeout as httpxConnectTimeout,
    ConnectError as httpxConnectError,
    ReadTimeout as httpxReadTimeout,
    ReadError as httpxReadError,
    TooManyRedirects as httpxTooManyRedirects,
)

from linksurf.common.constants import DEFAULT_USER_AGENT, MAX_REDIRECT_DEPTH
from linksurf.common.models import HTTPRequest, HTTPResponse, Redirect
from linksurf.common.settings import Settings
from linksurf.events import RequestEvent
from linksurf.events.bus import EventBus
from linksurf.logger import Logger
from linksurf.services.base import Service


class ConnectError(Exception):
    pass


class ConnectTimeoutError(Exception):
    pass


class ReadError(Exception):
    pass


class ReadTimeoutError(Exception):
    pass


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

        start_time = time.perf_counter()

        try:
            response = await self._client.request(
                method=request.method,
                url=request.url,
                headers=headers,
                timeout=request.timeout,
                follow_redirects=request.follow_redirects,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            match e:
                case httpxConnectTimeout():
                    error = "Connection timed out."
                    exception = ConnectTimeoutError(str(e))
                case httpxReadTimeout():
                    error = "Read timed out."
                    exception = ReadTimeoutError(str(e))
                case httpxReadError():
                    error = "Read error."
                    exception = ReadError(str(e))
                case httpxConnectError():
                    error = "Connect error."
                    exception = ConnectError(str(e))
                case httpxTooManyRedirects():
                    error = "Too many redirects."
                    exception = MaxRedirectsError(str(e))
                case _:
                    error = "Uncaught error."
                    exception = e

            exception_type = type(exception)
            exception_path = f"{exception_type.__module__}.{exception_type.__qualname__}"

            EventBus().emit(RequestEvent(
                scheme=scheme, url=request.url, method=request.method,
                duration_ms=duration_ms, error=error, exception=exception_path,
                correlation_id=request.metadata.correlation_id, component=request.metadata.component,
            ))

            raise exception from e

        self._client.cookies.clear()

        elapsed_ms = response.elapsed.total_seconds() * 1000

        EventBus().emit(RequestEvent(
            scheme=scheme, url=request.url, method=request.method,
            duration_ms=elapsed_ms, status_code=response.status_code,
            correlation_id=request.metadata.correlation_id, component=request.metadata.component,
        ))

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
