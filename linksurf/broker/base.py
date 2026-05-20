from typing import Any, Callable

from linksurf.components.base import Component


class Broker:
    components: list[Component]

    def connect(self):
        pass

    def disconnect(self):
        pass

    def pipeline(self, components: list[Component]):
        pass

    def seed(self, topic: str, data: Any):
        pass

    def subscribe(self, topic: str, handler: Callable[[Any], Any]):
        pass

    def publish(self, topic: str, data: Any):
        pass

    # Listens to topics and execute callbacks
    def loop(self):
        pass
