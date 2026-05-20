from typing import Any

from linksurf.common.types import Response
from linksurf.services import Services


class Consumer:
    CONSUMES_FROM: str


class Producer:
    PRODUCES_TO: str | list[str]


class Component[T](Consumer, Producer):
    def on_start(self, services: Services):
        pass

    def on_stop(self):
        pass

    def process(self, data: Any) -> Response[T]:
        # Called by the Broker when a message arrives on CONSUMES_FROM.
        # The return value is published to PRODUCES_TO or the error is caught.

        pass


class Executor:
    def on_start(self, services: Services):
        pass

    def on_stop(self):
        pass

    def execute(self, metadata: dict[str, Any]):
        pass




class MiddlewareResponse(Response[dict[str, Any]]):
    pass


# Enriches metadata
class Middleware(Executor):
    def execute(self, metadata: dict[str, Any]) -> MiddlewareResponse:
        pass


class FilterResponse(Response[bool]):
    pass


# Uses metadata to decide if URL should be skipped
class Filter(Executor):
    DEPENDS_ON: list[Middleware]

    def execute(self, metadata: dict[str, Any]) -> FilterResponse:
        pass


class PrioritizerResponse(Response[int]):
    pass


class Prioritizer(Executor):
    def execute(self, metadata) -> PrioritizerResponse:
        pass