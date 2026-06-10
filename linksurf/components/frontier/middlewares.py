import logging
from urllib.robotparser import RobotFileParser

from linksurf.common.models import HTTPRequest, MimeType
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse
from linksurf.services import Services, Fetcher, Cache
from linksurf.utils.dns import check_domain_availability

logger = logging.getLogger(__name__)


class DNSMiddleware(Middleware):
    """
    Queries the website's DNS to check availability and IP.
    """

    cache: Cache

    def on_start(self, services: Services):
        self.cache = services.cache

    def execute(self, payload: Payload) -> MiddlewareResponse:
        domain = payload.url.domain
        port = payload.url.port

        try:
            cached = self.cache.get_domain_status(domain, port)
        except Exception as e:
            logger.exception("Cache raised an exception for %s", payload.url.domain)

            return MiddlewareResponse(None, Error("Failed to retrieve domain status from cache.", retriable=True))

        if cached:
            available, ip = cached
        else:
            available, ip = check_domain_availability(domain, port)

            try:
                self.cache.save_domain_status(domain, port, available, ip)
            except Exception as e:
                logger.exception("Cache raised an exception for %s", payload.url.domain)

                return MiddlewareResponse(None, Error("Failed to save domain status to cache.", retriable=True))

        if not available or ip is None:
            return MiddlewareResponse(None, Error("URL is invalid or unreachable.", retriable=True))

        payload.add_metadata("dns", {"available": True, "ip": ip})

        return MiddlewareResponse(payload, None)


class CountryMiddleware(Middleware):
    """
    Computes the website's guessed country.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        raise NotImplementedError()


class RobotsExclusionMiddleware(Middleware):
    """
    Queries the website's robots.txt file and ensures page can be accessed.

    Follows (almost) all instructions described in [RFC 9309](https://datatracker.ietf.org/doc/html/rfc9309).
    """

    cache: Cache
    fetcher: Fetcher

    def on_start(self, services: Services):
        self.cache = services.cache
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        try:
            cached = self.cache.get_domain_robots_txt(payload.url.domain)
        except Exception as e:
            logger.exception("Cache raised an exception for %s", payload.url.domain)

            return MiddlewareResponse(None, Error("Failed to retrieve robots.txt from cache.", retriable=True))

        if cached:
            parser = self._build_parser(cached)

            can_fetch = parser.can_fetch("*", payload.url.address)
            delay = parser.crawl_delay("*")

            payload.add_metadata("robots", {"available": True, "can_fetch": can_fetch, "delay": delay})

            return MiddlewareResponse(payload, None)

        robots_url = f"{payload.url.origin}/robots.txt"

        request = HTTPRequest(url=robots_url)

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", robots_url)

            return MiddlewareResponse(None, Error("Fetch failed.", retriable=True))

        status = response.status_code

        if status == 403:
            return MiddlewareResponse(None, Error("robots.txt access denied.", retriable=True))

        if 400 <= status < 500:
            payload.add_metadata("robots", {"available": False, "can_fetch": True})

            return MiddlewareResponse(payload, None)

        if 500 <= status < 600:
            payload.add_metadata("robots", {"available": False, "can_fetch": False})

            return MiddlewareResponse(payload, None)

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        if mime_type != MimeType.TEXT:
            return MiddlewareResponse(None, Error("Invalid content type.", retriable=True))

        parser = self._build_parser(response.text)

        can_fetch = parser.can_fetch("*", payload.url.address)
        delay = parser.crawl_delay("*")

        try:
            self.cache.save_domain_robots_txt(payload.url.domain, response.text)
        except Exception as e:
            logger.exception("Cache raised an exception for %s", payload.url.domain)

            return MiddlewareResponse(None, Error("Failed to save robots.txt to cache.", retriable=True))

        payload.add_metadata("robots", {"available": True, "can_fetch": can_fetch, "delay": delay})

        return MiddlewareResponse(payload, None)

    def _build_parser(self, contents: str) -> RobotFileParser:
        parser = RobotFileParser()

        parser.parse(contents.splitlines())

        return parser
