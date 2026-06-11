import logging

from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Deduplicator, DeduplicatorResponse
from linksurf.services import Cache, Services

logger = logging.getLogger(__name__)


class URLDeduplicator(Deduplicator):
    cache: Cache

    def on_start(self, settings, services: Services):
        self.cache = services.cache

    def check(self, payload: Payload) -> DeduplicatorResponse:
        try:
            seen = self.cache.is_url_seen(payload.url)
        except Exception:
            logger.exception("Cache lookup failed for %s", payload.url.address)

            return DeduplicatorResponse(None, Error("Cache lookup failed.", retriable=True))

        return DeduplicatorResponse(seen, None)

    def register(self, payload: Payload) -> None:
        self.cache.mark_url_seen(payload.url)
