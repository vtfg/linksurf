from linksurf.common.payload import Payload
from linksurf.common.types import Response
from linksurf.components.base import Component
from linksurf.components.frontier.prioritizer import Prioritizer, MultiFactorPrioritizer
from linksurf.services import Services


class Frontier(Component[Payload]):
    CONSUMES_FROM = "url.process"
    PRODUCES_TO = "url.fetch"

    def __init__(self):
        super().__init__()

        self.prioritizer: Prioritizer = MultiFactorPrioritizer()

    def on_start(self, services: Services):
        super().on_start(services)

        self.prioritizer.on_start(services)

    def run(self, payload: Payload) -> Response[Payload]:
        priority_response = self.prioritizer.execute(payload)

        if priority_response.error is not None:
            return Response(None, priority_response.error)

        payload.priority = priority_response.data

        return Response(payload, None)
