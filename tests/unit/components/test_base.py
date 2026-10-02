import asyncio

import pytest

from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Component, RuleResponse, MiddlewareResponse, FilterResponse, PrioritizerResponse, \
    ConsumerComponent, LooperComponent
from tests.fakes.broker import FakeBroker
from tests.fakes.executors import FakeRule, FakeDeduplicator, FakeMiddleware, FakeFilter, FakePrioritizer


# TODO: Add tests for the _save_execution function

class TestBaseComponent:
    def test_initializes_with_default_elements(self):
        class FakeComponent(Component):
            pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        assert component.broker is broker
        assert len(component.rules) == 0
        assert component.deduplicator is None
        assert len(component.middlewares) == 0
        assert len(component.filters) == 0
        assert component.deduplicator is None
        assert component.NAME == "FakeComponent"

    def test_initializes_with_defined_name(self):
        class FakeComponent(Component):
            NAME = "MyFakeComponent"

        broker = FakeBroker()
        component = FakeComponent(broker)

        assert component.NAME == "MyFakeComponent"

    async def test_assign_database_and_start_executors(self, settings, services):
        rule = FakeRule()
        deduplicator = FakeDeduplicator()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()

        executors = [rule, deduplicator, middleware, filter, prioritizer]

        class FakeComponent(Component):
            def __init__(self, broker):
                super().__init__(broker)

                self.rules = [rule]
                self.deduplicator = deduplicator
                self.middlewares = [middleware]
                self.filters = [filter]
                self.prioritizer = prioritizer

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        assert component.database is services.database
        for executor in executors:
            assert executor.calls["on_start"] == 1

    async def test_stop_executors(self, settings, services):
        rule = FakeRule()
        deduplicator = FakeDeduplicator()
        middleware = FakeMiddleware()
        filter = FakeFilter()
        prioritizer = FakePrioritizer()

        executors = [rule, deduplicator, middleware, filter, prioritizer]

        class FakeComponent(Component):
            def __init__(self, broker):
                super().__init__(broker)

                self.rules = [rule]
                self.deduplicator = deduplicator
                self.middlewares = [middleware]
                self.filters = [filter]
                self.prioritizer = prioritizer

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_stop()

        for executor in executors:
            assert executor.calls["on_stop"] == 1

    async def test_executes_rule_and_emit_events(self, settings, services, listener):
        rule = FakeRule()

        class FakeComponent(Component):
            def __init__(self, broker):
                super().__init__(broker)

                self.rules = [rule]

        broker = FakeBroker()
        component = FakeComponent(broker)

        payload = Payload(url=URL("https://example.com"))

        await component.on_start(settings, services)

        rule.mock(RuleResponse(True, None))
        proceed, error = await component.rule(payload)

        assert proceed is True
        assert error is None
        assert rule.executions == [payload]
        assert listener.calls == {
            "rule.start": 1,
            "rule.finish": 1,
        }

        rule.mock(RuleResponse(None, Error("Something went wrong.")))
        proceed, error = await component.rule(payload)

        assert proceed is None
        assert error is not None
        assert error.message == "Something went wrong."
        assert rule.executions == [payload, payload]
        assert listener.calls == {
            "rule.start": 2,
            "rule.finish": 1,
            "rule.error": 1,
        }

    @pytest.mark.skip(reason="FakeDeduplicator not fully implemented")
    async def test_executes_deduplicator_and_emit_events(self, settings, services, listener):
        deduplicator = FakeDeduplicator()

        class FakeComponent(Component):
            pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        payload = Payload(url=URL("https://example.com"))

        await component.on_start(settings, services)

        with pytest.raises(Exception, match="Deduplicator not defined."):
            await component.deduplicate(payload)

        assert listener.calls == {}

        component.deduplicator = deduplicator

        # deduplicator.mock("check", DeduplicatorCheckResponse(False, None))
        # deduplicator.mock("register", None)
        seen, error = await component.deduplicate(payload)

        assert seen is False
        assert error is None
        assert deduplicator.executions == [payload]
        assert listener.calls == {
            "deduplicator.start": 1,
            "deduplicator.finish": 1,
        }

        # deduplicator.mock("check", DeduplicatorCheckResponse(False, None))
        # deduplicator.mock("register", Error("Something went wrong."))
        seen, error = await component.deduplicate(payload)

        assert seen is None
        assert error is not None
        assert error.message == "Something went wrong."
        assert deduplicator.executions == [payload, payload]
        assert listener.calls == {
            "deduplicator.start": 2,
            "deduplicator.finish": 1,
            "deduplicator.error": 1,
        }

    async def test_executes_middleware_and_emit_events(self, settings, services, listener):
        middleware = FakeMiddleware()

        class FakeComponent(Component):
            def __init__(self, broker):
                super().__init__(broker)

                self.middlewares = [middleware]

        broker = FakeBroker()
        component = FakeComponent(broker)

        payload = Payload(url=URL("https://example.com"))

        await component.on_start(settings, services)

        middleware.mock(MiddlewareResponse(payload, None))
        error = await component.enrich(payload)

        assert error is None
        assert middleware.executions == [payload]
        assert listener.calls == {
            "middleware.start": 1,
            "middleware.finish": 1,
        }

        middleware.mock(MiddlewareResponse(None, Error("Something went wrong.")))
        error = await component.enrich(payload)

        assert error is not None
        assert error.message == "Something went wrong."
        assert middleware.executions == [payload, payload]
        assert listener.calls == {
            "middleware.start": 2,
            "middleware.finish": 1,
            "middleware.error": 1,
        }

    async def test_executes_middleware_filter_and_emit_events(self, settings, services, listener):
        middleware = FakeMiddleware()
        filter = FakeFilter()

        class FakeComponent(Component):
            def __init__(self, broker):
                super().__init__(broker)

                self.middlewares = [middleware]
                self.filters = [filter]

        broker = FakeBroker()
        component = FakeComponent(broker)

        payload = Payload(url=URL("https://example.com"))

        await component.on_start(settings, services)

        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(True, None))
        proceed, error = await component.filter(payload)

        assert proceed is True
        assert error is None
        assert middleware.executions == [payload]
        assert filter.executions == [payload]
        assert listener.calls == {
            "middleware.start": 1,
            "middleware.finish": 1,
            "filter.start": 1,
            "filter.finish": 1,
        }

        middleware.mock(MiddlewareResponse(payload, Error("Something went wrong.")))
        filter.mock(FilterResponse(None, None))
        proceed, error = await component.filter(payload)

        assert proceed is None
        assert error is not None
        assert error.message == "Something went wrong."
        assert middleware.executions == [payload, payload]
        assert filter.executions == [payload]
        assert listener.calls == {
            "middleware.start": 2,
            "middleware.finish": 1,
            "middleware.error": 1,
            "filter.start": 1,
            "filter.finish": 1,
        }

        middleware.mock(MiddlewareResponse(payload, None))
        filter.mock(FilterResponse(None, Error("Something went wrong.")))
        proceed, error = await component.filter(payload)

        assert proceed is None
        assert error is not None
        assert error.message == "Something went wrong."
        assert middleware.executions == [payload, payload, payload]
        assert filter.executions == [payload, payload]
        assert listener.calls == {
            "middleware.start": 3,
            "middleware.finish": 2,
            "middleware.error": 1,
            "filter.start": 2,
            "filter.finish": 1,
            "filter.error": 1,
        }

    async def test_executes_prioritizer_and_emit_events(self, settings, services, listener):
        prioritizer = FakePrioritizer()

        class FakeComponent(Component):
            pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        payload = Payload(url=URL("https://example.com"))

        await component.on_start(settings, services)

        with pytest.raises(Exception, match="Prioritizer not defined."):
            await component.prioritize(payload)

        assert listener.calls == {}

        component.prioritizer = prioritizer

        prioritizer.mock(PrioritizerResponse(5, None))
        priority, error = await component.prioritize(payload)

        assert priority == 5
        assert error is None
        assert prioritizer.executions == [payload]
        assert listener.calls == {
            "prioritizer.start": 1,
            "prioritizer.finish": 1,
        }

        prioritizer.mock(PrioritizerResponse(None, Error("Something went wrong.")))
        priority, error = await component.prioritize(payload)

        assert priority is None
        assert error is not None
        assert error.message == "Something went wrong."
        assert prioritizer.executions == [payload, payload]
        assert listener.calls == {
            "prioritizer.start": 2,
            "prioritizer.finish": 1,
            "prioritizer.error": 1,
        }

    async def test_publishes_payload_to_broker(self, settings, services, listener):
        class FakeComponent(Component):
            pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        payload1 = Payload(url=URL("https://example.com/1"), priority=1)

        await component.publish("topic", payload1)

        assert listener.calls == {
            "component.publish": 1
        }
        assert broker.messages.get("topic") == [(payload1, 1)]

        payload2 = Payload(url=URL("https://example.com/2"), priority=2)
        payload3 = Payload(url=URL("https://example.com/3"), priority=3)

        await component.publish("topic", [payload2, payload3])

        assert listener.calls == {
            "component.publish": 2,
        }
        assert broker.messages.get("topic") == [(payload1, 1), (payload2, 2), (payload3, 3)]


class TestConsumerComponent:
    async def test_subscription_fails_when_concurrency_is_lower_than_one(self, settings, services, listener):
        class FakeComponent(ConsumerComponent):
            TOPIC = "topic"

            async def on_start(self, settings, services):
                await super().on_start(settings, services)

                await self.subscribe(self.TOPIC, self.consume, concurrency=0)

            async def consume(self, payload: Payload):
                pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        with pytest.raises(ValueError, match="Concurrency must be >= 1."):
            await component.on_start(settings, services)

    async def test_subscribes_using_broker(self, settings, services, listener):
        class FakeComponent(ConsumerComponent):
            TOPIC = "topic"

            async def on_start(self, settings, services):
                await super().on_start(settings, services)

                await self.subscribe(self.TOPIC, self.consume)

            async def consume(self, payload: Payload):
                pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        assert broker.handlers.get("topic") is not None
        assert listener.calls == {
            "component.subscribe": 1
        }

    async def test_executes_handler_when_subscribed_topic_receives_message(self, settings, services, listener):
        class FakeComponent(ConsumerComponent):
            TOPIC = "topic"

            async def on_start(self, settings, services):
                await super().on_start(settings, services)

                await self.subscribe(self.TOPIC, self.consume)

            async def consume(self, payload: Payload):
                pass

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        payload = Payload(url=URL("https://example.com/"), priority=1)

        await component.publish("topic", payload)

        assert broker.messages.get("topic") == [(payload, 1)]
        assert listener.calls == {
            "component.subscribe": 1,
            "component.publish": 1,
            "component.start": 1,
            "component.finish": 1,
        }

    async def test_emits_returned_error_when_handling_message(self, settings, services, listener):
        class FakeComponent(ConsumerComponent):
            TOPIC = "topic"

            async def on_start(self, settings, services):
                await super().on_start(settings, services)

                await self.subscribe(self.TOPIC, self.consume)

            async def consume(self, payload: Payload):
                return Error("Something went wrong.")

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        payload = Payload(url=URL("https://example.com/"), priority=1)

        await component.publish("topic", payload)

        assert listener.calls == {
            "component.subscribe": 1,
            "component.publish": 1,
            "component.start": 1,
            "component.error": 1,
        }

    async def test_catches_exceptions_when_handling_message(self, settings, services, listener):
        class FakeComponent(ConsumerComponent):
            TOPIC = "topic"

            async def on_start(self, settings, services):
                await super().on_start(settings, services)

                await self.subscribe(self.TOPIC, self.consume)

            async def consume(self, payload: Payload):
                raise Exception("Something went wrong.")

        broker = FakeBroker()
        component = FakeComponent(broker)

        await component.on_start(settings, services)

        payload = Payload(url=URL("https://example.com/"), priority=1)

        await component.publish("topic", payload)

        assert listener.calls == {
            "component.subscribe": 1,
            "component.publish": 1,
            "component.start": 1,
            "component.error": 1,
        }


class TestLooperComponent:
    async def test_processes_pulled_payload(self, listener):
        payload = Payload(URL("https://example.com"))
        received = []

        class FakeComponent(LooperComponent):
            async def pull(self):
                # allow only a single payload to process.
                self._looping = False

                return payload, "*"

            async def process(self, _payload, extra):
                received.append((_payload, extra))

                return None

        component = FakeComponent(FakeBroker())

        try:
            await component.loop(
                component.pull,
                component.process,
            )

            tasks = tuple(component._loop_tasks)

            await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=1,
            )

            assert received == [(payload, "*")]
            assert listener.calls == {
                "component.loop": 1,
                "component.start": 1,
                "component.finish": 1,
            }
        finally:
            await component.on_stop()

    async def test_emits_returned_error_when_handling_pulled_payload(self, listener):
        payload = Payload(URL("https://example.com"))

        class FakeComponent(LooperComponent):
            async def pull(self):
                self._looping = False

                return payload, "*"

            async def process(self, _payload, extra):
                return Error("Something went wrong.")

        component = FakeComponent(FakeBroker())

        try:
            await component.loop(
                component.pull,
                component.process,
            )

            await asyncio.wait_for(
                asyncio.gather(*component._loop_tasks),
                timeout=1,
            )

            assert listener.calls == {
                "component.loop": 1,
                "component.start": 1,
                "component.error": 1,
            }
        finally:
            await component.on_stop()

    async def test_catches_exceptions_when_handling_pulled_payload(self, listener):
        payload = Payload(URL("https://example.com"))

        class FakeComponent(LooperComponent):
            async def pull(self):
                self._looping = False

                return payload, "*"

            async def process(self, _payload, extra):
                raise Exception("Something went wrong.")

        component = FakeComponent(FakeBroker())

        try:
            await component.loop(
                component.pull,
                component.process,
            )

            await asyncio.wait_for(
                asyncio.gather(*component._loop_tasks),
                timeout=1,
            )

            assert listener.calls == {
                "component.loop": 1,
                "component.start": 1,
                "component.error": 1,
            }
        finally:
            await component.on_stop()

    async def test_waits_for_in_flight_processing(self):
        payload = Payload(URL("https://example.com"))
        processing_started = asyncio.Event()
        release_processing = asyncio.Event()

        class FakeComponent(LooperComponent):
            async def pull(self):
                return payload, "*"

            async def process(self, _payload, extra):
                processing_started.set()

                await release_processing.wait()

                return None

        component = FakeComponent(FakeBroker())
        stopping = None

        try:
            await component.loop(
                component.pull,
                component.process,
            )

            await asyncio.wait_for(
                processing_started.wait(),
                timeout=1,
            )

            stopping = asyncio.create_task(component.on_stop())

            # Allow on_stop() to reach the in-flight gather.
            await asyncio.sleep(0)

            assert not stopping.done()

            release_processing.set()

            await asyncio.wait_for(stopping, timeout=1)

            assert component._looping is False
            assert component._loop_tasks == []
            assert component._loop_in_flight == set()
        finally:
            release_processing.set()

            if stopping is not None and not stopping.done():
                await stopping

            if stopping is None:
                await component.on_stop()
