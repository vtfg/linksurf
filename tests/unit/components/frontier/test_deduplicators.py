from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.components.frontier.deduplicators import URLDeduplicator


class TestURLDeduplicator:
    async def test_assigns_cache_on_start(self, settings, services):
        deduplicator = URLDeduplicator()

        await deduplicator.on_start(settings, services)

        assert deduplicator.cache is services.cache

    async def test_checks_unseen_url(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("is_url_seen", False)

        await deduplicator.on_start(settings, services)

        response = await deduplicator.check(payload)

        assert response.seen is False
        assert response.error is None
        assert cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
        }

    async def test_checks_seen_url(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("is_url_seen", True)

        await deduplicator.on_start(settings, services)

        response = await deduplicator.check(payload)

        assert response.seen is True
        assert response.error is None
        assert cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
        }

    async def test_returns_error_when_cache_check_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("is_url_seen", exception)

        await deduplicator.on_start(settings, services)

        response = await deduplicator.check(payload)

        assert response.seen is None
        assert response.error is not None
        assert response.error.message == "Cache lookup failed."
        assert response.error.retriable is True
        assert response.error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
        }

    async def test_registers_url(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("mark_url_seen", None)

        await deduplicator.on_start(settings, services)

        error = await deduplicator.register(payload)

        assert error is None
        assert cache.calls == {
            "on_start": 1,
            "mark_url_seen": 1,
        }

    async def test_returns_error_when_registration_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("mark_url_seen", exception)

        await deduplicator.on_start(settings, services)

        error = await deduplicator.register(payload)

        assert error is not None
        assert error.message == "Cache write failed."
        assert error.retriable is True
        assert error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "mark_url_seen": 1,
        }

    async def test_unregisters_url(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("unmark_url_seen", None)

        await deduplicator.on_start(settings, services)

        error = await deduplicator.unregister(payload)

        assert error is None
        assert cache.calls == {
            "on_start": 1,
            "unmark_url_seen": 1,
        }

    async def test_returns_error_when_unregistration_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        deduplicator = URLDeduplicator()
        cache = services.cache

        cache.mock("unmark_url_seen", exception)

        await deduplicator.on_start(settings, services)

        error = await deduplicator.unregister(payload)

        assert error is not None
        assert error.message == "Cache write failed."
        assert error.retriable is True
        assert error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "unmark_url_seen": 1,
        }
