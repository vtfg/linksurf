from typing import Any, Callable

from linksurf.common.constants import MIN_QUEUE_PRIORITY


class Broker:
    async def connect(self):
        raise NotImplementedError()

    async def disconnect(self):
        raise NotImplementedError()

    async def seed(self, topic: str, data: Any):
        raise NotImplementedError()

    async def subscribe(self, topic: str, handler: Callable[[Any], Any], concurrency: int = 1):
        raise NotImplementedError()

    async def publish(self, topic: str, data: Any, priority: int = MIN_QUEUE_PRIORITY):
        raise NotImplementedError()

    async def delayed_publish(self, topic: str, data: Any, delay_seconds: int, priority: int = MIN_QUEUE_PRIORITY):
        raise NotImplementedError()

    async def loop(self):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()
