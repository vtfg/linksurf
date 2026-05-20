from typing import Any

from linksurf.common.types import Response
from linksurf.common.models import URL
from linksurf.components.base import Component
from linksurf.components.frontier.filters import Filter
from linksurf.components.frontier.middlewares import Middleware
from linksurf.components.frontier.prioritizer import Prioritizer, MultiFactorPrioritizer
from linksurf.services import Services


class Frontier(Component[tuple[URL, int]]):
    CONSUMES_FROM = "links"
    PRODUCES_TO = "urls"

    def __init__(self):
        super().__init__()

        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []

        self.prioritizer: Prioritizer = MultiFactorPrioritizer()

    def on_start(self, services: Services):
        self.prioritizer.on_start(services)

        for _middleware in self.middlewares:
            _middleware.on_start(services)

        for _filter in self.filters:
            _filter.on_start(services)

    def process(self, url: URL) -> Response[tuple[URL, int]]:
        metadata: dict[str, Any] = {"url": url}

        for _middleware in self.middlewares:
            response = _middleware.execute(metadata)

            if response.error is not None:
                continue

            if response.data is None:
                continue

            metadata.update(response.data)

        for _filter in self.filters:
            response = _filter.execute(metadata)

            if response.error is not None:
                return Response(None, response.error)

            if not response.data:
                continue

        prioritizer_response = self.prioritizer.execute(metadata)

        return Response((url, prioritizer_response.data), None)
