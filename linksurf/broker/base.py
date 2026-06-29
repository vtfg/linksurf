from typing import Any, Callable

from linksurf.common.constants import MIN_QUEUE_PRIORITY


class Broker:
    def connect(self):
        pass

    def disconnect(self):
        pass

    def seed(self, topic: str, data: Any):
        pass

    def subscribe(self, topic: str, handler: Callable[[Any], Any]):
        pass

    def publish(self, topic: str, data: Any, priority: int = MIN_QUEUE_PRIORITY):
        pass

    def delayed_publish(self, topic: str, data: Any, delay_seconds: int, priority: int = MIN_QUEUE_PRIORITY):
        pass

    # Listens to topics and execute callbacks
    def loop(self):
        pass

    def stop(self):
        pass
