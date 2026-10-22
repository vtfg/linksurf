import pytest

from linksurf.common.models import Country, URL
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import FilterResponse, MiddlewareResponse, PrioritizerResponse, RuleResponse
from linksurf.components.frontier import Frontier
from linksurf.components.frontier.deduplicators import URLDeduplicator
from linksurf.components.frontier.filters import CountryFilter, RobotsExclusionFilter
from linksurf.components.frontier.middlewares import CountryMiddleware, DNSMiddleware, RobotsExclusionMiddleware
from linksurf.components.frontier.prioritizers import MultiFactorPrioritizer
from linksurf.components.frontier.rules import (
    BLOCKED_EXTENSIONS,
    BlockedDomainsRule,
    SchemeRule,
    URLExtensionRule,
    URLLimitsRule,
)
from linksurf.services.database import URLModel
from linksurf.utils.hashing import bucketize
from tests.fakes.broker import FakeBroker
from tests.fakes.executors import FakeFilter, FakeMiddleware, FakePrioritizer, FakeRule


class TestFrontier:
    def test_initializes_pipeline(self):
        broker = FakeBroker()
        component = Frontier(broker)

        assert component.broker is broker
        assert component.NAME == "Frontier"
        assert component.TOPIC == "url.process"

        assert len(component.rules) == 4
        assert isinstance(component.rules[0], SchemeRule)
        assert component.rules[0].allowed == ["http", "https"]
        assert isinstance(component.rules[1], URLExtensionRule)
        assert component.rules[1].blocked == BLOCKED_EXTENSIONS
        assert isinstance(component.rules[2], URLLimitsRule)
        assert component.rules[2].max_length == 2048
        assert component.rules[2].max_path_depth == 10
        assert isinstance(component.rules[3], BlockedDomainsRule)
        assert component.rules[3].blocked == {"google.com", "iana.org"}

        assert isinstance(component.deduplicator, URLDeduplicator)

        assert len(component.middlewares) == 3
        assert isinstance(component.middlewares[0], DNSMiddleware)
        assert isinstance(component.middlewares[1], CountryMiddleware)
        assert isinstance(component.middlewares[2], RobotsExclusionMiddleware)

        assert len(component.filters) == 2
        assert isinstance(component.filters[0], CountryFilter)
        assert component.filters[0].allowed == [Country.BRAZIL]
        assert isinstance(component.filters[1], RobotsExclusionFilter)

        assert isinstance(component.prioritizer, MultiFactorPrioritizer)

    async def test_assigns_database_and_subscribes_on_start(self, settings, services, listener):
        broker = FakeBroker()
        component = Frontier(broker)
        component.rules = []
        component.deduplicator = None
        component.middlewares = []
        component.filters = []
        component.prioritizer = None

        await component.on_start(settings, services)

        handler, concurrency = broker.handlers[component.TOPIC]

        assert component.database is services.database
        assert callable(handler)
        assert concurrency == 100
        assert listener.calls == {
            "component.subscribe": 1,
        }

    async def test_stops_when_rule_rejects_payload(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(False, None))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is None
        assert payload.deduplicated is False
        assert rule.executions == [payload]
        assert middleware.executions == []
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
        }

    async def test_returns_rule_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Rule failed.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(None, Error("Rule failed.", exception=exception)))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Rule failed."
        assert error.exception is exception
        assert payload.deduplicated is False
        assert rule.executions == [payload]
        assert middleware.executions == []
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.error": 1,
        }

    async def test_returns_deduplicator_check_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", exception)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Cache lookup failed."
        assert error.retriable is True
        assert error.exception is exception
        assert payload.deduplicated is False
        assert rule.executions == [payload]
        assert middleware.executions == []
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.error": 1,
        }

    async def test_stops_when_url_was_already_seen(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", True)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is None
        assert payload.deduplicated is True
        assert rule.executions == [payload]
        assert middleware.executions == []
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
        }

    async def test_returns_deduplicator_registration_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Cache unavailable.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", exception)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Cache write failed."
        assert error.retriable is True
        assert error.exception is exception
        assert payload.deduplicated is False
        assert rule.executions == [payload]
        assert middleware.executions == []
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
            "mark_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.error": 1,
        }

    async def test_returns_middleware_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Middleware failed.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(None, Error("Middleware failed.", exception=exception)))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Middleware failed."
        assert error.exception is exception
        assert payload.deduplicated is True
        assert rule.executions == [payload]
        assert middleware.executions == [payload]
        assert filter.executions == []
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
            "mark_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.error": 1,
        }

    async def test_stops_when_filter_rejects_payload(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(False, None))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is None
        assert payload.deduplicated is True
        assert rule.executions == [payload]
        assert middleware.executions == [payload]
        assert filter.executions == [payload]
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
            "mark_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
        }

    async def test_returns_filter_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Filter failed.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(None, Error("Filter failed.", exception=exception)))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Filter failed."
        assert error.exception is exception
        assert payload.deduplicated is True
        assert rule.executions == [payload]
        assert middleware.executions == [payload]
        assert filter.executions == [payload]
        assert prioritizer.executions == []
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
            "mark_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.error": 1,
        }

    async def test_returns_prioritizer_error(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Prioritizer failed.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(None, Error("Prioritizer failed.", exception=exception)))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Prioritizer failed."
        assert error.exception is exception
        assert payload.priority == 0
        assert rule.executions == [payload]
        assert middleware.executions == [payload]
        assert filter.executions == [payload]
        assert prioritizer.executions == [payload]
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.error": 1,
        }

    async def test_returns_error_when_prioritizer_has_no_result(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(None, None))

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Prioritizer gave empty response."
        assert error.retriable is True
        assert payload.priority == 0
        assert prioritizer.executions == [payload]
        assert services.database.calls == {
            "on_start": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.error": 1,
        }

    async def test_bypasses_deduplication_when_payload_was_already_checked(self, settings, services, listener):
        payload = Payload(URL("https://example.com"), deduplicated=True)
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(3, None))
        services.database.mock("register_url", None)
        services.database.mock("save_domain", None)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is None
        assert payload.priority == 3
        assert services.cache.calls == {
            "on_start": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
            "register_url": 1,
            "save_domain": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.finish": 1,
            "crawl.pending": 1,
        }

    @pytest.mark.parametrize("priority", [0, 3])
    async def test_registers_accepted_url(self, priority, settings, services, listener):
        payload = Payload(URL("https://example.com/path"))
        registered_urls = []
        saved_domains = []
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        async def register_url(url):
            registered_urls.append(url)

        async def save_domain(domain, bucket):
            saved_domains.append((domain, bucket))

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(priority, None))
        services.database.mock("register_url", register_url)
        services.database.mock("save_domain", save_domain)

        await component.on_start(settings, services)

        error = await component.process(payload)

        bucket = bucketize(payload.url.domain)

        assert error is None
        assert payload.deduplicated is True
        assert payload.priority == priority
        assert registered_urls == [URLModel(
            address=payload.url.address,
            hash=payload.url.hash,
            domain=payload.url.domain,
            bucket=bucket,
            priority=priority,
            correlation_id=payload.correlation_id,
            discovered_at=payload.discovered_at,
        )]
        assert saved_domains == [(payload.url.domain, bucket)]
        assert rule.executions == [payload]
        assert middleware.executions == [payload]
        assert filter.executions == [payload]
        assert prioritizer.executions == [payload]
        assert services.cache.calls == {
            "on_start": 1,
            "is_url_seen": 1,
            "mark_url_seen": 1,
        }
        assert services.database.calls == {
            "on_start": 1,
            "register_url": 1,
            "save_domain": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.finish": 1,
            "crawl.pending": 1,
        }

    async def test_returns_error_when_url_registration_fails(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Database unavailable.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(3, None))
        services.database.mock("register_url", exception)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Database write failed."
        assert error.retriable is True
        assert error.exception is exception
        assert payload.priority == 3
        assert services.database.calls == {
            "on_start": 1,
            "register_url": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.finish": 1,
        }

    async def test_returns_error_when_domain_registration_fails(self, settings, services, listener):
        payload = Payload(URL("https://example.com"))
        exception = RuntimeError("Database unavailable.")
        rule = FakeRule()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()
        component = Frontier(FakeBroker())
        component.rules = [rule]
        component.middlewares = [middleware]
        component.filters = [filter]
        component.prioritizer = prioritizer

        rule.mock(RuleResponse(True, None))
        services.cache.mock("is_url_seen", False)
        services.cache.mock("mark_url_seen", None)
        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        prioritizer.mock(PrioritizerResponse(3, None))
        services.database.mock("register_url", None)
        services.database.mock("save_domain", exception)

        await component.on_start(settings, services)

        error = await component.process(payload)

        assert error is not None
        assert error.message == "Database write failed."
        assert error.retriable is True
        assert error.exception is exception
        assert payload.priority == 3
        assert services.database.calls == {
            "on_start": 1,
            "register_url": 1,
            "save_domain": 1,
        }
        assert listener.calls == {
            "component.subscribe": 1,
            "rule.start": 1,
            "rule.finish": 1,
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
            "prioritizer.start": 1,
            "prioritizer.finish": 1,
        }
