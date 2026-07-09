import time
from dataclasses import dataclass
from typing import Callable, NamedTuple, Awaitable

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_RETRIES, MIN_QUEUE_PRIORITY
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.events.bus import EventBus
from linksurf.logger import Logger
from linksurf.services import Services


class Executor:
    async def on_start(self, settings: Settings, services: Services):
        pass

    async def on_stop(self):
        pass

    async def execute(self, payload: Payload):
        raise NotImplementedError()


class MiddlewareResponse(Response[Payload]):
    pass


# Enriches metadata
class Middleware(Executor):
    async def execute(self, payload: Payload) -> MiddlewareResponse:
        raise NotImplementedError()


class RuleResponse(Response[bool]):
    pass


class Rule(Executor):
    async def execute(self, payload: Payload) -> RuleResponse:
        raise NotImplementedError()


class FilterResponse(Response[bool]):
    pass


# Uses metadata to decide if URL should be skipped
class Filter(Executor):
    DEPENDS_ON: list[Middleware]

    async def execute(self, payload: Payload) -> FilterResponse:
        raise NotImplementedError()


class PrioritizerResponse(Response[int]):
    pass


class Prioritizer(Executor):
    async def execute(self, payload: Payload) -> PrioritizerResponse:
        raise NotImplementedError()


class DeduplicatorCheckResponse(NamedTuple):
    seen: bool | None
    error: Error | None


@dataclass
class DeduplicatorRegisterResponse:
    error: Error | None


class Deduplicator:
    async def on_start(self, settings: Settings, services: Services):
        pass

    async def on_stop(self):
        pass

    async def check(self, payload: Payload) -> DeduplicatorCheckResponse:
        raise NotImplementedError()

    async def register(self, payload: Payload) -> Error | None:
        raise NotImplementedError()

    async def unregister(self, payload: Payload) -> Error | None:
        raise NotImplementedError()


class Component:
    TOPIC: str

    def __init__(self, broker: Broker) -> None:
        self.broker = broker

        self.rules: list[Rule] = []
        self.deduplicator: Deduplicator | None = None
        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []
        self.prioritizer: Prioritizer | None = None

        self._component_name = type(self).__name__

    async def on_start(self, settings: Settings, services: Services):
        for rule in self.rules:
            await rule.on_start(settings, services)

        if self.deduplicator is not None:
            await self.deduplicator.on_start(settings, services)

        for middleware in self.middlewares:
            await middleware.on_start(settings, services)

        for filter in self.filters:
            await filter.on_start(settings, services)

        if self.prioritizer is not None:
            await self.prioritizer.on_start(settings, services)

    async def on_stop(self):
        for rule in self.rules:
            await rule.on_stop()

        if self.deduplicator is not None:
            await self.deduplicator.on_stop()

        for middleware in self.middlewares:
            await middleware.on_stop()

        for filter in self.filters:
            await filter.on_stop()

        if self.prioritizer is not None:
            await self.prioritizer.on_stop()

    async def rule(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Executes all rules. Returns True if the component should continue executing.
        """

        from linksurf.events import (
            RuleStartEvent, RuleFinishEvent, RuleErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        for rule in self.rules:
            rule_name = type(rule).__name__

            EventBus().emit(
                RuleStartEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name))

            response = await rule.execute(payload)

            if response.error is not None:
                EventBus().emit(
                    RuleErrorEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name,
                                   error=response.error.message, retriable=response.error.retriable,
                                   exception=response.error.exception))

                return None, response.error

            EventBus().emit(
                RuleFinishEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name,
                                passed=bool(response.data)))

            if not response.data:
                return False, None

        return True, None

    async def deduplicate(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Checks if duplicate and registers if not.
        """

        if self.deduplicator is None:
            raise Exception("Deduplicator not defined.")

        from linksurf.events import (
            DeduplicatorStartEvent, DeduplicatorFinishEvent, DeduplicatorErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__
        deduplicator_name = type(self.deduplicator).__name__

        EventBus().emit(DeduplicatorStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                               deduplicator=deduplicator_name))

        response = await self.deduplicator.check(payload)

        if response.error is not None:
            EventBus().emit(
                DeduplicatorErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                       deduplicator=deduplicator_name, error=response.error.message,
                                       retriable=response.error.retriable, exception=response.error.exception))

            return None, response.error

        if response.seen:
            EventBus().emit(
                DeduplicatorFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        deduplicator=deduplicator_name, seen=True))

            return True, None

        error = await self.deduplicator.register(payload)

        if error is not None:
            EventBus().emit(
                DeduplicatorErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                       deduplicator=deduplicator_name, error=error.message,
                                       retriable=error.retriable, exception=error.exception))

            return False, error

        EventBus().emit(
            DeduplicatorFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                    deduplicator=deduplicator_name, seen=False))

        return False, None

    async def enrich(self, payload: Payload) -> Error | None:
        """
        Executes all middlewares. Updates payload in place.
        """

        from linksurf.events import (
            MiddlewareStartEvent, MiddlewareFinishEvent, MiddlewareErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        for middleware in self.middlewares:
            middleware_name = type(middleware).__name__
            metadata_snapshot = dict(payload.metadata)

            EventBus().emit(MiddlewareStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                 middleware=middleware_name))

            response = await middleware.execute(payload)

            if response.error is not None:
                EventBus().emit(
                    MiddlewareErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                         middleware=middleware_name,
                                         error=response.error.message,
                                         retriable=response.error.retriable,
                                         exception=response.error.exception))

                return response.error

            metadata_diff = {k: v for k, v in payload.metadata.items() if metadata_snapshot.get(k) != v}

            EventBus().emit(
                MiddlewareFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                      middleware=middleware_name, data=metadata_diff))

        return None

    async def filter(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Executes all middlewares and filters. Returns True if the component should continue executing.
        """

        from linksurf.events import (
            FilterStartEvent, FilterFinishEvent, FilterErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        error = await self.enrich(payload)

        if error is not None:
            return None, error

        for filter in self.filters:
            filter_name = type(filter).__name__

            EventBus().emit(
                FilterStartEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name))

            response = await filter.execute(payload)

            if response.error is not None:
                EventBus().emit(
                    FilterErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                     filter=filter_name, error=response.error.message,
                                     retriable=response.error.retriable,
                                     exception=response.error.exception))

                return None, response.error

            EventBus().emit(
                FilterFinishEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name,
                                  passed=bool(response.data)))

            if not response.data:
                return False, None

        return True, None

    async def prioritize(self, payload: Payload) -> tuple[int | None, Error | None]:
        """
        Calculates and returns a priority number.
        """

        if self.prioritizer is None:
            raise Exception("Prioritizer not defined.")

        from linksurf.events import (
            PrioritizerStartEvent, PrioritizerFinishEvent, PrioritizerErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__
        prioritizer_name = type(self.prioritizer).__name__

        EventBus().emit(PrioritizerStartEvent(
            correlation_id=correlation_id, url=url,
            component=component_name, prioritizer=prioritizer_name,
        ))

        response = await self.prioritizer.execute(payload)

        if response.error is not None:
            EventBus().emit(PrioritizerErrorEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
                error=response.error.message,
                retriable=response.error.retriable,
                exception=response.error.exception,
            ))

            return None, response.error

        if not response.data:
            error = Error("Prioritizer gave empty response.", retriable=True)

            EventBus().emit(PrioritizerErrorEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
                error=error.message,
                retriable=error.retriable,
                exception=error.exception,
            ))

            return None, error

        EventBus().emit(PrioritizerFinishEvent(
            correlation_id=correlation_id, url=url,
            component=component_name, prioritizer=prioritizer_name,
            priority=response.data,
        ))

        return response.data, None

    async def subscribe(self, topic: str, callback: Callable[[Payload], Awaitable[Error | None]],
                        concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("Concurrency must be >= 1.")

        from linksurf.events import ComponentSubscribeEvent

        component_name = type(self).__name__

        EventBus().emit(ComponentSubscribeEvent(component=component_name, topic=topic))

        async def handler(data: Payload):
            from linksurf.events import (
                ComponentStartEvent, ComponentFinishEvent, ComponentErrorEvent,
            )

            correlation_id = data.correlation_id
            url = data.url.address
            start_time = time.perf_counter()

            if data.retrying:
                # increment before processing so events reflect the current retry count
                data.retries += 1

            EventBus().emit(ComponentStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                topic=topic, retrying=data.retrying, retries=data.retries))

            try:
                error = await callback(data)
            except Exception as e:
                error = Error("Uncaught error.", exception=e, retriable=False, unexpected=True)

            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000

            if error is not None:
                EventBus().emit(
                    ComponentErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        error=error.message,
                                        retriable=error.retriable,
                                        retrying=data.retrying,
                                        retries=data.retries,
                                        unexpected=error.unexpected,
                                        exception=error.exception))

                if error.retriable and data.retries < MAX_RETRIES:
                    data.retrying = True

                    if error.delay_seconds:
                        await self.delayed_publish(self.TOPIC, data, error.delay_seconds)
                    else:
                        await self.publish(self.TOPIC, data)
                else:
                    Logger().warning(
                        "component.discard",
                        url=data.url.address,
                        topic=self.TOPIC,
                        retries=data.retries,
                        reason=error.message,
                        retriable=error.retriable,
                    )

                return

            EventBus().emit(
                ComponentFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                     topic=topic, duration_ms=duration_ms,
                                     retrying=data.retrying, retries=data.retries))

        await self.broker.subscribe(topic, handler)

    async def publish(self, topic: str, data: Payload | list[Payload], priority: int | None = None) -> None:
        from linksurf.events import ComponentPublishEvent

        payloads = data if isinstance(data, list) else [data]

        for payload in payloads:
            self._prepare_publish(topic, payload, priority)

            await self.broker.publish(topic, payload, payload.priority)

        EventBus().emit(ComponentPublishEvent(
            component=self._component_name, topic=topic,
            urls=[(payload.url.address, payload.priority) for payload in payloads],
        ))

    async def delayed_publish(self, topic: str, payload: Payload, delay_seconds: int,
                              priority: int | None = None) -> None:
        from linksurf.events import ComponentPublishEvent

        self._prepare_publish(topic, payload, priority)

        EventBus().emit(ComponentPublishEvent(
            component=self._component_name, topic=topic,
            urls=[(payload.url.address, payload.priority)], delay=delay_seconds,
        ))

        await self.broker.delayed_publish(topic, payload, delay_seconds, payload.priority)

    def _prepare_publish(self, topic: str, payload: Payload, priority: int | None) -> None:
        if priority is not None:
            payload.priority = priority

        if topic != self.TOPIC:
            payload.retrying = False
            payload.retries = 0
        else:
            payload.priority = max(MIN_QUEUE_PRIORITY, payload.priority - 1)
