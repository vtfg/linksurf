from linksurf.common.models import Content
from linksurf.components.base import Component


class Parser(Component):
    CONSUMES_FROM = "page.parse"
    PRODUCES_TO = ["url.process", "page.store"]

    def __init__(self):
        super().__init__()

    def process(self, content: Content):
        pass
