from linksurf.common.payload import Payload
from linksurf.common.types import Response
from linksurf.components.base import Component, Filter


class Storage(Component[Payload]):
    CONSUMES_FROM = "page.store"

    def __init__(self):
        super().__init__()

        self.filters: list[Filter] = []

    def run(self, payload: Payload) -> Response[Payload]:
        pass
