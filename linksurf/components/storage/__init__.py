from linksurf.broker.base import Broker
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import ConsumerComponent
from linksurf.services import Services
from linksurf.services.cache import Cache


class Storage(ConsumerComponent):
    NAME = "Storage"
    TOPIC = "url.store"

    cache: Cache

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.filters = [
            # ContentSeenFilter(),
        ]

    async def on_start(self, settings: Settings, services: Services):
        await super().on_start(settings, services)

        self.cache = services.cache

        await self.subscribe(self.TOPIC, self.store, concurrency=10)

    async def store(self, payload: Payload) -> Error | None:
        if payload.content is None or payload.response is None:
            return Error("Payload has no content or response.", retriable=False)

        try:
            await self.cache.update_domain_metrics(
                payload.url.domain,
                payload.url.port,
                payload.response.elapsed_ms,
                payload.response.size_bytes,
            )
        except Exception as e:
            return Error("Cache write failed.", retriable=True, exception=e)

        # Storage is the final pipeline component.

        return None
