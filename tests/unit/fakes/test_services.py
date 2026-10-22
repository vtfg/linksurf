import pytest

from linksurf.common.models import URL
from tests.fakes.services import FakeCache


class TestFakeService:
    async def test_counts_function_calls(self):
        cache = FakeCache()

        await cache.on_start(object())
        
        await cache.on_stop()

        assert cache.calls == {
            "on_start": 1,
            "on_stop": 1,
        }

    async def test_returns_mocked_result(self):
        cache = FakeCache()
        url = URL("https://example.com")

        cache.mock("is_url_seen", True)

        result = await cache.is_url_seen(url)

        assert result is True
        assert cache.calls == {
            "is_url_seen": 1,
        }

    async def test_raises_when_calling_function_that_was_never_mocked(self):
        cache = FakeCache()
        url = URL("https://example.com")

        with pytest.raises(NotImplementedError):
            await cache.is_url_seen(url)

        assert cache.calls == {
            "is_url_seen": 1,
        }

    async def test_replaces_existing_mocked_result(self):
        cache = FakeCache()
        url = URL("https://example.com")

        cache.mock("is_url_seen", False)
        first = await cache.is_url_seen(url)

        cache.mock("is_url_seen", True)
        second = await cache.is_url_seen(url)

        assert first is False
        assert second is True
        assert cache.calls["is_url_seen"] == 2

    async def test_raises_mocked_exception(self):
        cache = FakeCache()
        url = URL("https://example.com")

        cache.mock("is_url_seen", RuntimeError("Service not started."))

        with pytest.raises(RuntimeError, match="Service not started."):
            await cache.is_url_seen(url)

        assert cache.calls["is_url_seen"] == 1

    async def test_accepts_async_callable_result(self):
        cache = FakeCache()
        url = URL("https://example.com")

        async def result(checked_url):
            assert checked_url is url

            return True

        cache.mock("is_url_seen", result)

        assert await cache.is_url_seen(url) is True

    def test_rejects_non_function_attribute(self):
        cache = FakeCache()

        with pytest.raises(TypeError, match="'calls' is not a function"):
            cache.mock("calls", None)
