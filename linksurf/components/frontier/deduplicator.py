from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Deduplicator, DeduplicatorCheckResponse
from linksurf.services import Cache, Services


class URLDeduplicator(Deduplicator):
    cache: Cache

    def on_start(self, settings, services: Services):
        self.cache = services.cache

    def check(self, payload: Payload) -> DeduplicatorCheckResponse:
        try:
            seen = self.cache.is_url_seen(payload.url)
        except Exception as e:
            return DeduplicatorCheckResponse(None, Error("Cache lookup failed.", retriable=True, exception=e))

        return DeduplicatorCheckResponse(seen, None)

    def register(self, payload: Payload) -> Error | None:
        try:
            self.cache.mark_url_seen(payload.url)
        except Exception as e:
            return Error("Cache lookup failed.", retriable=True, exception=e)

        return None

    def unregister(self, payload: Payload) -> Error | None:
        try:
            self.cache.unmark_url_seen(payload.url)
        except Exception as e:
            return Error("Cache write failed.", retriable=True, exception=e)

        return None

