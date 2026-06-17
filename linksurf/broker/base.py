from typing import Any, Callable

from linksurf.common.payload import Payload
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

    def subscribe(self, topic: str, handler: Callable[[Payload], None]):
        pass

    def publish(self, topic: str, data: Any):
        pass

    def delayed_publish(self, topic: str, data: Any, delay_seconds: int):
        pass

    # Listens to topics and execute callbacks
    def loop(self):
        pass

    def stop(self):
        pass
