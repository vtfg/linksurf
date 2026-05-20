from typing import Any

from linksurf.components.base import Component, Filter


class Storage(Component):
    CONSUMES_FROM = "contents"

    def __init__(self):
        super().__init__()

        self.filters: list[Filter] = []

    def process(self, data: Any) -> None:
        pass
