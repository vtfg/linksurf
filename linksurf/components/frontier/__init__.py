from linksurf.broker.base import Broker
from linksurf.common.models import Country
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import ConsumerComponent
from linksurf.components.frontier.deduplicator import URLDeduplicator
from linksurf.components.frontier.filters import RobotsExclusionFilter, CountryFilter
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, DNSMiddleware, CountryMiddleware
from linksurf.components.frontier.prioritizer import MultiFactorPrioritizer
from linksurf.components.frontier.rules import (
    SchemeRule,
    URLExtensionRule,
    URLLimitsRule,
    BlockedDomainsRule,
    BLOCKED_EXTENSIONS,
)
from linksurf.events import CrawlPendingEvent
from linksurf.events.bus import EventBus
from linksurf.hashing import bucketize
from linksurf.services import Services, Database
from linksurf.services.database import URLModel


class Frontier(ConsumerComponent):
    NAME = "Frontier"
    TOPIC = "url.process"

    database: Database

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.rules = [
            SchemeRule(allowed=["http", "https"]),
            URLExtensionRule(blocked=BLOCKED_EXTENSIONS),
            URLLimitsRule(max_length=2048, max_path_depth=10),
            BlockedDomainsRule(blocked=["google.com", "iana.org"]),
        ]
        self.deduplicator = URLDeduplicator()
        self.middlewares = [
            DNSMiddleware(),
            CountryMiddleware(),
            RobotsExclusionMiddleware(),
        ]
        self.filters = [
            CountryFilter(allowed=[Country.BRAZIL]),
            RobotsExclusionFilter(),
        ]
        self.prioritizer = MultiFactorPrioritizer()

    async def on_start(self, settings: Settings, services: Services) -> None:
        await super().on_start(settings, services)

        self.database = services.database

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

        payload.priority = priority

        url = URLModel(
            address=payload.url.address,
            hash=payload.url.hash,
            domain=payload.url.domain,
            bucket=bucketize(payload.url),
            priority=payload.priority or 0,
            correlation_id=payload.correlation_id,
            discovered_at=payload.discovered_at,
        )

        try:
            await self.database.register_url(url)
            await self.database.save_domain(payload.url.domain)
        except Exception as e:
            return Error("Database write failed.", retriable=True, exception=e)

        await EventBus().emit(
            CrawlPendingEvent(correlation_id=payload.correlation_id, component=self.NAME, url=url.address))

        return None
