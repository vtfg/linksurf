import logging
from urllib.robotparser import RobotFileParser

from linksurf.common.fixture import COUNTRIES
from linksurf.common.models import HTTPRequest, URL
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse
from linksurf.services import Services, Fetcher, Cache
from linksurf.utils.url import normalize_url

logger = logging.getLogger(__name__)


class DNSMiddleware(Middleware):
    """
    Queries the website's DNS and checks availability, IP, etc.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        pass


class CountryMiddleware(Middleware):
    """
    Computes the website's guessed country.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        _ = payload.url.domain
        _ = payload.get_metadata("ip")

        # Check domain TLD, fetch server IP location, etc.

        payload.add_metadata("country", COUNTRIES["bra"])

        return MiddlewareResponse(payload, None)


class RobotsExclusionMiddleware(Middleware):
    """
    Queries the website's robots.txt file and ensures page can be accessed.
    """

    cache: Cache
    fetcher: Fetcher

    def on_start(self, services: Services):
        self.cache = services.cache
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        if payload.url.scheme not in ["http", "https"]:
            return MiddlewareResponse(None, Error("Scheme not supported.", retriable=False))

        try:
            cached = self.cache.get_domain_robots_txt(payload.url.domain)
        except Exception as e:
            logger.exception("Cache raised an exception for %s", payload.url.domain)

            return MiddlewareResponse(None, Error("Failed to retrieve robots.txt from cache.", retriable=True))

        if cached:
            parser = self._build_parser(cached)

            can_fetch = parser.can_fetch("*", payload.url.address)

            payload.add_metadata("robots", {"available": True, "can_fetch": can_fetch})

            return MiddlewareResponse(payload, None)

        robots_url = f"{payload.url.origin}/robots.txt"

        request = HTTPRequest(url=robots_url)

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", robots_url)

            return MiddlewareResponse(None, Error("Fetch failed.", retriable=True))

        status = response.status_code

        if 400 <= status < 500:
            payload.add_metadata("robots", {"available": False, "can_fetch": True})

            return MiddlewareResponse(payload, None)

        if 500 <= status < 600:
            payload.add_metadata("robots", {"available": False, "can_fetch": False})

            return MiddlewareResponse(payload, None)

        if not "text/plain" in response.headers.get("Content-Type", ""):
            return MiddlewareResponse(None, Error("Invalid content type.", retriable=True))

        parser = self._build_parser(response.text)

        can_fetch = parser.can_fetch("*", payload.url.address)

        try:
            self.cache.save_domain_robots_txt(payload.url.domain, response.text)
        except Exception as e:
            logger.exception("Cache raised an exception for %s", payload.url.domain)

            return MiddlewareResponse(None, Error("Failed to save robots.txt to cache.", retriable=True))

        payload.add_metadata("robots", {"available": True, "can_fetch": can_fetch})

        return MiddlewareResponse(payload, None)

    def _build_parser(self, contents: str) -> RobotFileParser:
        parser = RobotFileParser()

        parser.parse(contents.splitlines())

        return parser


class URLNormalizationMiddleware(Middleware):
    """
    Normalizes the URL by removing default ports, tracking parameters, fragments and sorting parameters.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        normalized = normalize_url(payload.url.address)

        payload.url = URL(address=normalized)

        return MiddlewareResponse(payload, None)
