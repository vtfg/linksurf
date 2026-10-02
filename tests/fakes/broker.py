from collections import defaultdict
from typing import Any, Callable

from linksurf.broker.base import Broker
from linksurf.common.constants import MIN_QUEUE_PRIORITY


class FakeBroker(Broker):
    def __init__(self):
        self.handlers: dict[str, tuple[Callable[[Any], Any], int]] = {}
        self.messages: dict[str, list[tuple[Any, int]]] = defaultdict(list)

    async def subscribe(self, topic: str, handler: Callable[[Any], Any], concurrency: int = 1):
        self.handlers[topic] = (handler, concurrency)

    async def publish(self, topic: str, data: Any, priority: int = MIN_QUEUE_PRIORITY):
        self.messages[topic].append((data, priority))

        if self.handlers.get(topic):
            await self.handlers[topic][0](data)
