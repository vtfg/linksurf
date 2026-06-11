import logging
import time

from linksurf.common.models import HTTPRequest
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse
from linksurf.services import Fetcher, Cache, Services

logger = logging.getLogger(__name__)


class ContentTypeMiddleware(Middleware):
    """
    Retrieves the URL's content type from the response headers.
    """

    fetcher: Fetcher

    def on_start(self, settings, services):
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        url = payload.url.address

        request = HTTPRequest(url, method="HEAD")

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", url)

            return MiddlewareResponse(None, Error("Fetch failed.", retriable=True))

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        if mime_type is None:
            return MiddlewareResponse(None, Error("Unknown content type.", retriable=True))

        payload.add_metadata("content_type", mime_type)

        return MiddlewareResponse(payload, None)


class RateLimiterMiddleware(Middleware):
    """
    Enforces per-domain crawl delays. Uses the Crawl-delay from robots.txt when
    available, falling back to a configured default.

    :param default_delay The default delay between crawls in seconds.
    """

    cache: Cache

    def __init__(self, default_delay: float = 1.0):
        self.default_delay = default_delay

    def on_start(self, settings, services: Services):
        self.cache = services.cache

    def execute(self, payload: Payload) -> MiddlewareResponse:
        domain = payload.url.domain
        port = payload.url.port

        robots = payload.get_metadata("robots") or {}
        delay = robots.get("delay") or self.default_delay

        try:
            last_fetch = self.cache.get_domain_last_fetch(domain, port)
        except Exception:
            logger.exception("Cache raised an exception for %s", domain)

            return MiddlewareResponse(None, Error("Failed to retrieve last fetch time from cache.", retriable=True))

        if last_fetch is not None:
            elapsed = time.monotonic() - last_fetch

            if elapsed < delay:
                print(f"Waiting {delay - elapsed} seconds")

                time.sleep(delay - elapsed)

        try:
            self.cache.save_domain_last_fetch(domain, port, time.monotonic())
        except Exception:
            logger.exception("Cache raised an exception for %s", domain)

            return MiddlewareResponse(None, Error("Failed to save last fetch time to cache.", retriable=True))

        return MiddlewareResponse(payload, None)


class ContentLengthMiddleware(Middleware):
    """
    Retrieves and parses the URL's content length from the response headers as bytes.
    """

    fetcher: Fetcher

    def on_start(self, settings, services):
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        url = payload.url.address

        request = HTTPRequest(url, method="HEAD")

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", url)

            return MiddlewareResponse(None, Error("Fetch failed.", retriable=True))

        raw_length = response.content_length

        chunked = "chunked" in response.headers.get("Transfer-Encoding", "").lower()

        if chunked:
            payload.add_metadata("content_length", {"value": None, "chunked": True})

            return MiddlewareResponse(payload, None)

        if raw_length is None:
            payload.add_metadata("content_length", {"value": None, "chunked": False})

            return MiddlewareResponse(payload, None)

        try:
            length = self._parse_length(raw_length)
        except Exception:
            logger.exception("Content-Length parse failed for %s", url)

            return MiddlewareResponse(None, Error("Invalid content length.", retriable=False))

        payload.add_metadata("content_length", {"value": length, "chunked": False})

        return MiddlewareResponse(payload, None)

    def _parse_length(self, raw: str) -> int:
        if "," in raw:
            parts = [p.strip() for p in raw.split(",")]

            if len(set(parts)) > 1:
                raise ValueError("Conflicting Content-Length headers")

            value = parts[0]
        else:
            value = raw

        try:
            size = int(value)
        except ValueError:
            raise ValueError(f"Invalid Content-Length format: {value!r}")

        if size < 0:
            raise ValueError("Negative Content-Length")

        return size
