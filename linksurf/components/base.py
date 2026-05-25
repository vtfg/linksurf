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
        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []

    def on_start(self, services: Services):
        for middleware in self.middlewares:
            middleware.on_start(services)

        for filter_ in self.filters:
            filter_.on_start(services)

    def on_stop(self):
        pass

    @final
    def process(self, payload: Payload) -> Response[T]:
        for middleware in self.middlewares:
            response = middleware.execute(payload)

            if response.error is not None:
                return Response(None, response.error)

        for filter_ in self.filters:
            response = filter_.execute(payload)

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
