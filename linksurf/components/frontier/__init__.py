from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.components.base import Component, Deduplicator
from linksurf.components.frontier.deduplicator import URLDeduplicator
from linksurf.components.frontier.prioritizer import Prioritizer, MultiFactorPrioritizer
from linksurf.events.bus import EventBus
from linksurf.logger import Logger
from linksurf.services import Services


class Frontier(Component[Payload]):
    CONSUMES_FROM = "url.process"
    PRODUCES_TO = "url.fetch"

    def __init__(self):
        super().__init__()

        self.deduplicator: Deduplicator = URLDeduplicator()
        self.prioritizer: Prioritizer = MultiFactorPrioritizer()

    def on_start(self, settings: Settings, services: Services, event_bus: EventBus):
        super().on_start(settings, services, event_bus)

        self.prioritizer.on_start(settings, services)

    def run(self, payload: Payload) -> Response[Payload]:
        priority_response = self.prioritizer.execute(payload)

        if priority_response.error is not None:
            return Response(None, priority_response.error)

        payload.priority = priority_response.data

        try:
            self.deduplicator.register(payload)
        except Exception:
            Logger().exception(f"Failed to mark URL as seen.")

            return Response(None, Error("Failed to mark URL as seen.", retriable=True))

        return Response(payload, None)
