from linksurf.common.payload import Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.components.frontier.deduplicator import URLDeduplicator
from linksurf.components.frontier.prioritizer import MultiFactorPrioritizer


class Frontier(Component[Payload]):
    CONSUMES_FROM = "url.process"
    PRODUCES_TO = "url.fetch"

    def __init__(self):
        super().__init__()

        self.deduplicator = URLDeduplicator()
        self.prioritizer = MultiFactorPrioritizer()

    def run(self, payload: Payload) -> Response[Payload]:
        try:
            self.deduplicator.register(payload)
        except Exception as e:
            return Response(None, Error("Cache write failed.", retriable=True, exception=e))

        return Response(payload, None)
