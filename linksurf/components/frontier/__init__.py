import logging

from linksurf.common.payload import Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.components.frontier.prioritizer import Prioritizer, MultiFactorPrioritizer
from linksurf.services import Services, Cache

logger = logging.getLogger(__name__)


class Frontier(Component[Payload]):
    CONSUMES_FROM = "url.process"
    PRODUCES_TO = "url.fetch"

    cache: Cache

    def __init__(self):
        super().__init__()

        self.prioritizer: Prioritizer = MultiFactorPrioritizer()

    def on_start(self, services: Services):
        super().on_start(services)

        self.prioritizer.on_start(services)

        self.cache = services.cache

    def run(self, payload: Payload) -> Response[Payload]:
        priority_response = self.prioritizer.execute(payload)

        if priority_response.error is not None:
            return Response(None, priority_response.error)

        payload.priority = priority_response.data

        try:
            self.cache.mark_url_seen(payload.url)
        except Exception as e:
            logger.exception("Failed to mark url (%s) as seen", payload.url.address)

            return Response(None, Error("Failed to mark URL as seen.", retriable=True))

        return Response(payload, None)
