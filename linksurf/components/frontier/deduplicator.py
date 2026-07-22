from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Deduplicator, DeduplicatorCheckResponse
from linksurf.services import Cache, Services


class URLDeduplicator(Deduplicator):
    cache: Cache

    async def on_start(self, settings, services: Services):
        self.cache = services.cache

    async def check(self, payload: Payload) -> DeduplicatorCheckResponse:
        try:
            seen = await self.cache.is_url_seen(payload.url)
        except Exception as e:
            return DeduplicatorCheckResponse(None, Error("Cache lookup failed.", retriable=True, exception=e))

        return DeduplicatorCheckResponse(seen, None)

    async def register(self, payload: Payload) -> Error | None:
        try:
            await self.cache.mark_url_seen(payload.url)
        except Exception as e:
            return Error("Cache lookup failed.", retriable=True, exception=e)

        return None

    async def unregister(self, payload: Payload) -> Error | None:
        try:
            await self.cache.unmark_url_seen(payload.url)
        except Exception as e:
            return Error("Cache write failed.", retriable=True, exception=e)

        return None
