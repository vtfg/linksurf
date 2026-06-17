import time
from typing import final

from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response
from linksurf.events.bus import EventBus
from linksurf.services import Services


class Consumer:
    CONSUMES_FROM: str


class Producer:
    PRODUCES_TO: str | list[str]


class Component[T](Consumer, Producer):
    event_bus: EventBus

    def __init__(self):
        self.rules: list[Rule] = []
        self.deduplicator: Deduplicator | None = None
        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []
        self.prioritizer: Prioritizer | None = None

    def on_start(self, settings: Settings, services: Services, event_bus: EventBus):
        self.event_bus = event_bus

        for rule in self.rules:
            rule.on_start(settings, services)

        if self.deduplicator is not None:
            self.deduplicator.on_start(settings, services)

        for middleware in self.middlewares:
            middleware.on_start(settings, services)

        for filter in self.filters:
            filter.on_start(settings, services)

        if self.prioritizer is not None:
            self.prioritizer.on_start(settings, services)

    def on_stop(self):
        pass

    @final
    def process(self, payload: Payload) -> Response[T]:
        from linksurf.events import (
            ComponentStartEvent, ComponentFinishEvent, ComponentErrorEvent,
            RuleStartEvent, RuleFinishEvent,
            DeduplicatorStartEvent, DeduplicatorFinishEvent, DeduplicatorErrorEvent,
            MiddlewareStartEvent, MiddlewareFinishEvent, MiddlewareErrorEvent,
            FilterStartEvent, FilterFinishEvent, FilterErrorEvent,
            PrioritizerStartEvent, PrioritizerFinishEvent, PrioritizerErrorEvent,
        )

        correlation_id = payload.url.hash
        url = payload.url.address
        component_name = type(self).__name__
        start_time = time.monotonic()

        self.event_bus.emit(ComponentStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                retrying=payload.retrying, retries=payload.retries))

        for rule in self.rules:
            rule_name = type(rule).__name__

            self.event_bus.emit(
                RuleStartEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name))

            response = rule.execute(payload)

            self.event_bus.emit(
                RuleFinishEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name,
                                passed=bool(response.data) and response.error is None))

            if response.error is not None:
                return Response(None, response.error)

            if not response.data:
                return Response(None, None)

        if self.deduplicator is not None:
            deduplicator_name = type(self.deduplicator).__name__

            self.event_bus.emit(DeduplicatorStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                       deduplicator=deduplicator_name))

            response = self.deduplicator.check(payload)

            if response.error is not None:
                self.event_bus.emit(
                    DeduplicatorErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                           deduplicator=deduplicator_name, error=response.error.message,
                                           retriable=response.error.retriable, exception=response.error.exception))

                return Response(None, response.error)

            self.event_bus.emit(
                DeduplicatorFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        deduplicator=deduplicator_name, seen=bool(response.data)))

            if response.data:
                return Response(None, None)

        for middleware in self.middlewares:
            middleware_name = type(middleware).__name__
            metadata_snapshot = dict(payload.metadata)

            self.event_bus.emit(MiddlewareStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                     middleware=middleware_name))

            response = middleware.execute(payload)

            if response.error is not None:
                self.event_bus.emit(
                    MiddlewareErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                         middleware=middleware_name,
                                         error=response.error.message,
                                         retriable=response.error.retriable,
                                         exception=response.error.exception))

                return Response(None, response.error)

            metadata_diff = {k: v for k, v in payload.metadata.items() if metadata_snapshot.get(k) != v}

            self.event_bus.emit(
                MiddlewareFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                      middleware=middleware_name, data=metadata_diff))

        for filter_ in self.filters:
            filter_name = type(filter_).__name__

            self.event_bus.emit(
                FilterStartEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name))

            response = filter_.execute(payload)

            if response.error is not None:
                self.event_bus.emit(
                    FilterErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                     filter=filter_name, error=response.error.message,
                                     retriable=response.error.retriable,
                                     exception=response.error.exception))

                return Response(None, response.error)

            self.event_bus.emit(
                FilterFinishEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name,
                                  passed=bool(response.data)))

            if not response.data:
                return Response(None, None)

        result = self.run(payload)

        duration_ms = (time.monotonic() - start_time) * 1000

        if result.error is not None:
            self.event_bus.emit(
                ComponentErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                    error=result.error.message,
                                    retriable=result.error.retriable,
                                    retrying=payload.retrying,
                                    retries=payload.retries,
                                    exception=result.error.exception))
            return result

        if self.prioritizer is not None:
            prioritizer_name = type(self.prioritizer).__name__

            self.event_bus.emit(PrioritizerStartEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
            ))

            response = self.prioritizer.execute(result.data)

            if response.error is not None:
                self.event_bus.emit(PrioritizerErrorEvent(
                    correlation_id=correlation_id, url=url,
                    component=component_name, prioritizer=prioritizer_name,
                    error=response.error.message,
                    retriable=response.error.retriable,
                    exception=response.error.exception,
                ))
                return Response(None, response.error)

            result.data.priority = response.data

            self.event_bus.emit(PrioritizerFinishEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
                priority=response.data,
            ))

        self.event_bus.emit(
            ComponentFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                 duration_ms=duration_ms,
                                 retrying=payload.retrying,
                                 retries=payload.retries))

        return result

    def run(self, payload: Payload) -> Response[T]:
        pass


class Executor:
    def on_start(self, settings: Settings, services: Services):
        pass

    def on_stop(self):
        pass

    def execute(self, payload: Payload):
        pass


class MiddlewareResponse(Response[Payload]):
    pass


# Enriches metadata
class Middleware(Executor):
    def execute(self, payload: Payload) -> MiddlewareResponse:
        pass


class RuleResponse(Response[bool]):
    pass


class Rule(Executor):
    def execute(self, payload: Payload) -> RuleResponse:
        pass


class FilterResponse(Response[bool]):
    pass


# Uses metadata to decide if URL should be skipped
class Filter(Executor):
    DEPENDS_ON: list[Middleware]

    def execute(self, payload: Payload) -> FilterResponse:
        pass


class PrioritizerResponse(Response[int]):
    pass


class Prioritizer(Executor):
    def execute(self, payload: Payload) -> PrioritizerResponse:
        pass


class DeduplicatorResponse(Response[bool]):
    pass


class Deduplicator:
    def on_start(self, settings: Settings, services: Services):
        pass

    def on_stop(self):
        pass

    def check(self, payload: Payload) -> DeduplicatorResponse:
        pass

    def register(self, payload: Payload) -> None:
        pass
