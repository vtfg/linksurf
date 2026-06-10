from typing import final

from linksurf.common.payload import Payload
from linksurf.common.types import Response
from linksurf.services import Services


class Consumer:
    CONSUMES_FROM: str


class Producer:
    PRODUCES_TO: str | list[str]


class Component[T](Consumer, Producer):
    def __init__(self):
        self.rules: list[Rule] = []
        self.deduplicator: Deduplicator | None = None
        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []

    def on_start(self, services: Services):
        for rule in self.rules:
            rule.on_start(services)

        if self.deduplicator is not None:
            self.deduplicator.on_start(services)

        for middleware in self.middlewares:
            middleware.on_start(services)

        for filter in self.filters:
            filter.on_start(services)

    def on_stop(self):
        pass

    @final
    def process(self, payload: Payload) -> Response[T]:
        for rule in self.rules:
            response = rule.execute(payload)

            if response.error is not None:
                return Response(None, response.error)

            if not response.data:
                return Response(None, None)

        if self.deduplicator is not None:
            response = self.deduplicator.check(payload)

            if response.error is not None:
                return Response(None, response.error)

            if response.data:
                return Response(None, None)

        for middleware in self.middlewares:
            response = middleware.execute(payload)

            if response.error is not None:
                return Response(None, response.error)

        for filter in self.filters:
            response = filter.execute(payload)

            if response.error is not None:
                return Response(None, response.error)

            if not response.data:
                return Response(None, None)

        return self.run(payload)

    def run(self, payload: Payload) -> Response[T]:
        pass


class Executor:
    def on_start(self, services: Services):
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
    def on_start(self, services: Services):
        pass

    def on_stop(self):
        pass

    def check(self, payload: Payload) -> DeduplicatorResponse:
        pass

    def register(self, payload: Payload) -> None:
        pass
