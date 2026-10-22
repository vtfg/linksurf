from linksurf.common.models import URL, HTTPResponse, HTTPRequest
from linksurf.common.payload import Payload
from linksurf.components.frontier import RobotsExclusionMiddleware
from linksurf.components.frontier.middlewares import REDIRECT_LOOP_STATUS_CODE
from linksurf.services.cache import RobotsRecord, ONE_DAY_IN_SECONDS
from linksurf.services.fetcher import MaxRedirectsError

# TODO: Create tests for other Middlewares
"""
DNSMiddleware uses socket and socks. It should use an interface instead of a function.

CountryMiddleware's IPInfoClient response can be mocked through the Fetcher. 
"""


class TestRobotsExclusionMiddleware:
    async def test_assigns_properties_on_start(self, settings, services):
        middleware = RobotsExclusionMiddleware()

        await middleware.on_start(settings, services)

        assert middleware.identifier is settings.identifier
        assert middleware.cache is services.cache
        assert middleware.fetcher is services.fetcher

    async def test_uses_cached_record(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt",
                   RobotsRecord(status_code=200, content_type="text/plain", text="User-agent: *\nDisallow:"))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert payload.get_metadata("robots") == {
            "available": True, "can_fetch": True, "delay": None, "cache_hit": True,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_returns_error_when_cache_lookup_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt", exception)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "Cache lookup failed."
        assert response.error.retriable is True
        assert response.error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_uses_freshly_fetched_record(self, settings, services):
        record: RobotsRecord | None = None
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache
        fetcher = services.fetcher

        def save_domain_robots_txt(_, __, status_code: int, content_type: str | None, text: str):
            nonlocal record
            record = RobotsRecord(status_code=status_code, content_type=content_type, text=text)

        def http_request(request: HTTPRequest) -> HTTPResponse:
            return HTTPResponse(
                url=request.url,
                status_code=200,
                headers={"Content-Type": "text/plain"},
                body="User-agent: *\nDisallow:".encode("utf-8"),
                encoding="utf-8",
                elapsed_ms=100,
                redirects=[],
                request=request,
            )

        cache.mock("get_domain_robots_txt", None)
        cache.mock("save_domain_robots_txt", save_domain_robots_txt)
        fetcher.mock("http", http_request)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert record is not None
        assert record.status_code == 200
        assert record.content_type == "text/plain"
        assert record.text == "User-agent: *\nDisallow:"
        assert payload.get_metadata("robots") == {
            "available": True, "can_fetch": True, "delay": None, "cache_hit": False,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
            "save_domain_robots_txt": 1,
        }
        assert fetcher.calls == {
            "on_start": 1,
            "http": 1,
        }

    async def test_ignores_text_if_fetched_record_status_code_is_not_200(self, settings, services):
        record: RobotsRecord | None = None
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache
        fetcher = services.fetcher

        def save_domain_robots_txt(_, __, status_code: int, content_type: str | None, text: str):
            nonlocal record
            record = RobotsRecord(status_code=status_code, content_type=content_type, text=text)

        def http_request(request: HTTPRequest) -> HTTPResponse:
            return HTTPResponse(
                url=request.url,
                status_code=404,
                headers={"Content-Type": "text/html"},
                body="<html><body><h1>File not found.</h1></body></html>".encode("utf-8"),
                encoding="utf-8",
                elapsed_ms=100,
                redirects=[],
                request=request,
            )

        cache.mock("get_domain_robots_txt", None)
        cache.mock("save_domain_robots_txt", save_domain_robots_txt)
        fetcher.mock("http", http_request)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert record is not None
        assert record.status_code == 404
        assert record.content_type == "text/html"
        assert record.text == ""
        assert payload.get_metadata("robots") == {
            "available": False, "can_fetch": True, "delay": None, "cache_hit": False,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
            "save_domain_robots_txt": 1,
        }
        assert fetcher.calls == {
            "on_start": 1,
            "http": 1,
        }

    async def test_returns_error_when_fetch_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Fetch failed.")
        middleware = RobotsExclusionMiddleware()
        cache = services.cache
        fetcher = services.fetcher

        cache.mock("get_domain_robots_txt", None)
        fetcher.mock("http", exception)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "HTTP fetch failed."
        assert response.error.retriable is True
        assert response.error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }
        assert fetcher.calls == {
            "on_start": 1,
            "http": 1,
        }

    async def test_returns_error_when_cache_write_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        middleware = RobotsExclusionMiddleware()
        cache = services.cache
        fetcher = services.fetcher

        def http_request(request: HTTPRequest) -> HTTPResponse:
            return HTTPResponse(
                url=request.url,
                status_code=200,
                headers={"Content-Type": "text/plain"},
                body="User-agent: *\nDisallow:".encode("utf-8"),
                encoding="utf-8",
                elapsed_ms=100,
                redirects=[],
                request=request,
            )

        cache.mock("get_domain_robots_txt", None)
        cache.mock("save_domain_robots_txt", exception)
        fetcher.mock("http", http_request)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "Cache write failed."
        assert response.error.retriable is True
        assert response.error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
            "save_domain_robots_txt": 1,
        }
        assert fetcher.calls == {
            "on_start": 1,
            "http": 1,
        }

    async def test_returns_error_when_status_code_is_403(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt", RobotsRecord(status_code=403, content_type="text/html", text=""))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "Robots Exclusion Protocol access denied."
        assert response.error.retriable is True
        assert response.error.delay_seconds is ONE_DAY_IN_SECONDS
        assert response.error.exception is None
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_returns_error_when_status_code_is_429(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt", RobotsRecord(status_code=429, content_type="text/html", text=""))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "Robots Exclusion Protocol rate limited."
        assert response.error.retriable is True
        assert response.error.delay_seconds is ONE_DAY_IN_SECONDS
        assert response.error.exception is None
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_permissive_when_fetch_reaches_more_than_five_redirects(self, settings, services):
        exception = MaxRedirectsError()
        payload = Payload(url=URL("https://example.com"))
        record: RobotsRecord | None = None
        middleware = RobotsExclusionMiddleware()
        cache = services.cache
        fetcher = services.fetcher

        def save_domain_robots_txt(_, __, status_code: int, content_type: str | None, text: str):
            nonlocal record
            record = RobotsRecord(status_code=status_code, content_type=content_type, text=text)

        cache.mock("get_domain_robots_txt", None)
        cache.mock("save_domain_robots_txt", save_domain_robots_txt)
        fetcher.mock("http", exception)

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert record is not None
        assert record.status_code == REDIRECT_LOOP_STATUS_CODE
        assert record.content_type is None
        assert record.text == ""
        assert payload.get_metadata("robots") == {
            "available": False, "can_fetch": True, "delay": None, "cache_hit": False,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
            "save_domain_robots_txt": 1,
        }
        assert fetcher.calls == {
            "on_start": 1,
            "http": 1,
        }

    async def test_permissive_when_status_code_is_404(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt", RobotsRecord(status_code=404, content_type="text/html", text=""))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert payload.get_metadata("robots") == {
            "available": False, "can_fetch": True, "delay": None, "cache_hit": True,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_blocks_when_status_code_is_500(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt", RobotsRecord(status_code=500, content_type="text/html", text=""))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert payload.get_metadata("robots") == {
            "available": False, "can_fetch": False, "delay": None, "cache_hit": True,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_permissive_when_content_type_is_not_plain_text(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt",
                   RobotsRecord(status_code=200, content_type="text/html; charset=utf-8",
                                text="User-agent: *\nDisallow: /"))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert payload.get_metadata("robots") == {
            "available": False, "can_fetch": True, "delay": None, "cache_hit": True,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }

    async def test_blocks_correctly_when_not_allowed(self, settings, services):
        payload = Payload(url=URL("https://example.com/protected"))
        middleware = RobotsExclusionMiddleware()
        cache = services.cache

        cache.mock("get_domain_robots_txt",
                   RobotsRecord(status_code=200, content_type="text/plain", text="User-agent: *\nDisallow: /protected"))

        await middleware.on_start(settings, services)

        response = await middleware.execute(payload)

        assert response.data is payload
        assert response.error is None
        assert payload.get_metadata("robots") == {
            "available": True, "can_fetch": False, "delay": None, "cache_hit": True,
        }
        assert cache.calls == {
            "on_start": 1,
            "get_domain_robots_txt": 1,
        }
