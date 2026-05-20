from linksurf.common.models import Content
from linksurf.components.base import Component


class Parser(Component):
    CONSUMES_FROM = "files"
    PRODUCES_TO = ["links", "contents"]

    def __init__(self):
        super().__init__()

    def process(self, content: Content):
        pass
