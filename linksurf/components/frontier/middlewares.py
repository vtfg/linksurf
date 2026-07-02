from urllib.robotparser import RobotFileParser

from linksurf.common.models import HTTPRequest, MimeType
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse
from linksurf.services import Services, Fetcher, Cache
from linksurf.services.cache import ONE_DAY_IN_SECONDS, RobotsRecord
from linksurf.services.fetcher import MaxRedirectsError
from linksurf.utils.dns import check_domain_availability

# sentinel status code used when robots.txt couldn't be fetched due to a redirect loop
REDIRECT_LOOP_STATUS_CODE = 0


class DNSMiddleware(Middleware):
    """
    Queries the website's DNS to check availability and IP.
    """

    cache: Cache

    def on_start(self, settings, services: Services):
        self.cache = services.cache

    def execute(self, payload: Payload) -> MiddlewareResponse:
        domain = payload.url.domain
        port = payload.url.port

        try:
            cached = self.cache.get_domain_status(domain, port)
        except Exception as e:
            return MiddlewareResponse(None, Error("Cache lookup failed.", retriable=True, exception=e))

        if cached:
            available, ip = cached
        else:
            available, ip = check_domain_availability(domain, port)

            try:
                self.cache.save_domain_status(domain, port, available, ip)
            except Exception as e:
                return MiddlewareResponse(None, Error("Cache write failed.", retriable=True, exception=e))

        if not available or ip is None:
            return MiddlewareResponse(None, Error("URL is invalid or unreachable.", retriable=True,
                                                  delay_seconds=ONE_DAY_IN_SECONDS))

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

    The raw robots.txt result (status code, content type, body) is always cached, regardless of
    outcome, so that a domain we already know to be unreachable, forbidden, or erroring doesn't get
    re-fetched for every URL. Cached and freshly-fetched records go through the same validation logic.
    """

    identifier: str

    cache: Cache
    fetcher: Fetcher

    def on_start(self, settings: Settings, services: Services):
        self.identifier = settings.identifier

        self.cache = services.cache
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        try:
            record = self.cache.get_domain_robots_txt(payload.url.domain, payload.url.port)
        except Exception as e:
            return MiddlewareResponse(None, Error("Cache lookup failed.", retriable=True, exception=e))

        if record is None:
            record, error = self._fetch(payload)

            if error is not None:
                return MiddlewareResponse(None, error)

            try:
                self.cache.save_domain_robots_txt(payload.url.domain, payload.url.port, record.status_code,
                                                  record.content_type,
                                                  record.text)
            except Exception as e:
                return MiddlewareResponse(None, Error("Cache write failed.", retriable=True, exception=e))

        available, can_fetch, delay, error = self._validate(record, payload.url.address)

        if error is not None:
            return MiddlewareResponse(None, error)

        payload.add_metadata("robots", {"available": available, "can_fetch": can_fetch, "delay": delay})

        return MiddlewareResponse(payload, None)

    def _fetch(self, payload: Payload) -> tuple[RobotsRecord | None, Error | None]:
        robots_url = f"{payload.url.origin}/robots.txt"

        request = HTTPRequest(url=robots_url, follow_redirects=True)

        try:
            response = self.fetcher.http(request)
        except MaxRedirectsError:
            return RobotsRecord(status_code=REDIRECT_LOOP_STATUS_CODE, content_type=None, text=""), None
        except Exception as e:
            return None, Error("HTTP fetch failed.", retriable=True, exception=e)

        text = response.text if response.status_code == 200 else ""

        return RobotsRecord(status_code=response.status_code, content_type=response.content_type, text=text), None

    def _validate(self, record: RobotsRecord, url: str) -> tuple[bool, bool, float | None, Error | None]:
        """
        Validates a robots.txt record (cached or freshly fetched) and returns (available, can_fetch, delay, error).
        """

        if record.status_code == 403:
            return False, False, None, Error("Robots Exclusion Protocol access denied.", retriable=True,
                                             delay_seconds=ONE_DAY_IN_SECONDS)

        if record.status_code == 429:
            return False, False, None, Error("Robots Exclusion Protocol rate limited.", retriable=True,
                                             delay_seconds=ONE_DAY_IN_SECONDS)

        if record.status_code == REDIRECT_LOOP_STATUS_CODE:
            return False, True, None, None

        if 400 <= record.status_code < 500:
            return False, True, None, None

        if 500 <= record.status_code < 600:
            return False, False, None, None

        if record.status_code == 200:
            content_type = record.content_type.split(";")[0].strip() if record.content_type else None

            if content_type != MimeType.TEXT:
                return False, True, None, None

            parser = self._build_parser(record.text)

            can_fetch = parser.can_fetch(self.identifier, url)
            delay = parser.crawl_delay(self.identifier)

            return True, can_fetch, delay, None

        # unexpected status code: block requests until the cache entry expires
        return False, False, None, None

    def _build_parser(self, contents: str) -> RobotFileParser:
        parser = RobotFileParser()

        parser.parse(contents.splitlines())

        return parser
