import logging

from linksurf.common.payload import Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component, Deduplicator
from linksurf.components.frontier.deduplicator import URLDeduplicator
from linksurf.components.frontier.prioritizer import Prioritizer, MultiFactorPrioritizer
from linksurf.services import Services

logger = logging.getLogger(__name__)


class Frontier(Component[Payload]):
    CONSUMES_FROM = "url.process"
    PRODUCES_TO = "url.fetch"

    def __init__(self):
        super().__init__()

        self.deduplicator: Deduplicator = URLDeduplicator()
        self.prioritizer: Prioritizer = MultiFactorPrioritizer()

    def on_start(self, services: Services):
        super().on_start(services)

        self.prioritizer.on_start(services)

    def run(self, payload: Payload) -> Response[Payload]:
        priority_response = self.prioritizer.execute(payload)

        if priority_response.error is not None:
            return Response(None, priority_response.error)

        payload.priority = priority_response.data

        try:
            self.deduplicator.register(payload)
        except Exception:
            logger.exception("Failed to mark URL %s as seen", payload.url.address)

            return Response(None, Error("Failed to mark URL as seen.", retriable=True))

        return Response(payload, None)
