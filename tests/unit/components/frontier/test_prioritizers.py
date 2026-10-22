import pytest

from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.components.frontier import MultiFactorPrioritizer
from linksurf.services.cache import DomainMetrics


class TestMultiFactorPrioritizer:
    @pytest.mark.parametrize(
        ("path_depth", "expected"),
        [
            (0, 5),
            (1, 4),
            (4, 1),
            (5, 0),
            (10, 0),
        ],
    )
    def test_calculates_path_score(self, path_depth, expected):
        prioritizer = MultiFactorPrioritizer()

        assert prioritizer._path_score(path_depth) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("", 5),
            ("a=1", 4),
            ("a=1&b=2", 3),
            ("a=1&b=2&c=3&d=4&e=5", 0),
            ("a=1&b=2&c=3&d=4&e=5&f=6", 0),
        ],
    )
    def test_calculates_query_score(self, query, expected):
        prioritizer = MultiFactorPrioritizer()

        assert prioritizer._query_score(query) == expected

    @pytest.mark.parametrize(
        ("avg_ms", "expected"),
        [
            (None, 2),
            (199, 5),
            (200, 4),
            (499, 4),
            (500, 3),
            (999, 3),
            (1000, 2),
            (1999, 2),
            (2000, 1),
            (4999, 1),
            (5000, 0),
        ],
    )
    def test_calculates_response_time_score(self, avg_ms, expected):
        prioritizer = MultiFactorPrioritizer()

        assert prioritizer._response_time_score(avg_ms) == expected

    @pytest.mark.parametrize(
        ("total_crawled", "expected"),
        [
            (None, 2),
            (9, 5),
            (10, 4),
            (49, 4),
            (50, 3),
            (199, 3),
            (200, 2),
            (499, 2),
            (500, 1),
            (999, 1),
            (1000, 0),
        ],
    )
    def test_calculates_crawl_count_score(self, total_crawled, expected):
        prioritizer = MultiFactorPrioritizer()

        assert prioritizer._crawl_count_score(total_crawled) == expected

    async def test_assigns_cache_on_start(self, settings, services):
        prioritizer = MultiFactorPrioritizer()

        await prioritizer.on_start(settings, services)

        assert prioritizer.cache is services.cache

    async def test_uses_url_factors_only(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        prioritizer = MultiFactorPrioritizer()
        cache = services.cache

        cache.mock("get_domain_metrics", None)

        await prioritizer.on_start(settings, services)

        response = await prioritizer.execute(payload)

        assert response.error is None
        assert response.data == 4
        assert services.cache.calls == {
            "on_start": 1,
            "get_domain_metrics": 1,
        }

    async def test_uses_metrics_and_url_factors(self, settings, services):
        payload = Payload(url=URL("https://example.com:8443/a/b?one=1&two=2"))
        prioritizer = MultiFactorPrioritizer()
        cache = services.cache

        cache.mock("get_domain_metrics", DomainMetrics(
            total_crawled=50,
            avg_response_ms=500,
            avg_content_size=1000,
        ))

        await prioritizer.on_start(settings, services)

        response = await prioritizer.execute(payload)

        assert response.error is None
        assert response.data == 3
        assert cache.calls == {
            "on_start": 1,
            "get_domain_metrics": 1,
        }

    async def test_returns_maximum_priority(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        prioritizer = MultiFactorPrioritizer()
        cache = services.cache

        cache.mock("get_domain_metrics", DomainMetrics(
            total_crawled=9,
            avg_response_ms=199,
            avg_content_size=1000,
        ))

        await prioritizer.on_start(settings, services)

        response = await prioritizer.execute(payload)

        assert response.error is None
        assert response.data == 5
        assert cache.calls == {
            "on_start": 1,
            "get_domain_metrics": 1,
        }

    async def test_returns_minimum_priority(self, settings, services):
        payload = Payload(url=URL(
            "https://example.com/a/b/c/d/e?one=1&two=2&three=3&four=4&five=5"
        ))
        prioritizer = MultiFactorPrioritizer()
        cache = services.cache

        cache.mock("get_domain_metrics", DomainMetrics(
            total_crawled=1000,
            avg_response_ms=5000,
            avg_content_size=1000,
        ))

        await prioritizer.on_start(settings, services)

        response = await prioritizer.execute(payload)

        assert response.error is None
        assert response.data == 0
        assert cache.calls == {
            "on_start": 1,
            "get_domain_metrics": 1,
        }

    async def test_returns_error_when_cache_query_fails(self, settings, services):
        payload = Payload(url=URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        prioritizer = MultiFactorPrioritizer()
        cache = services.cache

        cache.mock("get_domain_metrics", exception)

        await prioritizer.on_start(settings, services)

        response = await prioritizer.execute(payload)

        assert response.data is None
        assert response.error is not None
        assert response.error.message == "Cache lookup failed."
        assert response.error.retriable is True
        assert response.error.exception is exception
        assert cache.calls == {
            "on_start": 1,
            "get_domain_metrics": 1,
        }
