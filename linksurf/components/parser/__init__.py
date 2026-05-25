from linksurf.common.payload import Payload
from linksurf.common.types import Response
from linksurf.components.base import Component


class Parser(Component[Payload]):
    CONSUMES_FROM = "page.parse"
    PRODUCES_TO = ["url.process", "page.store"]

    def __init__(self):
        super().__init__()

    def run(self, payload: Payload) -> Response[Payload]:
        pass
