from linksurf.backqueue import BackQueue
from linksurf.broker.base import Broker
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.frontier.deduplicator import URLDeduplicator
from linksurf.components.frontier.filters import RobotsExclusionFilter
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, DNSMiddleware
from linksurf.components.frontier.prioritizer import MultiFactorPrioritizer
from linksurf.components.frontier.rules import (
    SchemeRule,
    URLExtensionRule,
    URLLimitsRule,
    BlockedDomainsRule,
    BLOCKED_EXTENSIONS,
)
from linksurf.services import Services


class Frontier(Component):
    TOPIC = "url.process"

    back_queue: BackQueue

    def __init__(self, broker: Broker, back_queue: BackQueue):
        super().__init__(broker)

        self.back_queue = back_queue

        self.rules = [
            SchemeRule(allowed=["http", "https"]),
            URLExtensionRule(blocked=BLOCKED_EXTENSIONS),
            URLLimitsRule(max_length=2048, max_path_depth=10),
            BlockedDomainsRule(blocked=["google.com", "iana.org"]),
        ]
        self.deduplicator = URLDeduplicator()
        self.middlewares = [
            DNSMiddleware(),
            # CountryMiddleware(),
            RobotsExclusionMiddleware(),
        ]
        self.filters = [
            RobotsExclusionFilter(),
        ]
        self.prioritizer = MultiFactorPrioritizer()

    async def on_start(self, settings: Settings, services: Services) -> None:
        await super().on_start(settings, services)

        await self.subscribe(self.TOPIC, self.process, concurrency=100)

    async def process(self, payload: Payload) -> Error | None:
        proceed, error = await self.rule(payload)

        if error is not None:
            return error

        if not proceed:
            return None

        seen, error = await self.deduplicate(payload)

        if error is not None:
            return error

        if seen:
            return None

        proceed, error = await self.filter(payload)

        if error is not None:
            return error

        if not proceed:
            return None

        priority, error = await self.prioritize(payload)

        if error is not None:
            return error

        await self.back_queue.put(payload)

        return None
