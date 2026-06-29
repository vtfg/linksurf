from dataclasses import asdict
from datetime import datetime, timezone

from linksurf.broker.base import Broker
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.services import Services
from linksurf.services.cache import Cache
from linksurf.services.database import Database


class Storage(Component):
    TOPIC = "url.store"

    database: Database
    cache: Cache

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.filters = [
            # ContentSeenFilter(),
        ]

    def on_start(self, settings: Settings, services: Services):
        super().on_start(settings, services)

        self.database = services.database
        self.cache = services.cache

        self.subscribe(self.TOPIC, self.store)

    def store(self, payload: Payload) -> Error | None:
        if payload.content is None or payload.response is None:
            return Error("Payload has no content or response.", retriable=False)

        data = self._build_data(payload)

        try:
            storage_id = self.database.save_url(data)
        except Exception as e:
            return Error("Database write failed.", retriable=True, exception=e)

        payload.storage_id = storage_id

        try:
            self.cache.update_domain_metrics(
                payload.url.domain,
                payload.url.port,
                payload.response.elapsed_ms,
                payload.response.size_bytes,
            )
        except Exception as e:
            return Error("Cache write failed.", retriable=True, exception=e)

        # Storage doesn't publish to anything

        return None

    def _build_data(self, payload: Payload) -> dict:
        return {
            "address": payload.url.address,
            "hash": payload.url.hash,
            "domain": payload.url.domain,
            "request": asdict(payload.request) if payload.request else None,
            "response": asdict(payload.response) if payload.response else None,
            "content": asdict(payload.content) if payload.content else None,
            "redirects": [asdict(r) for r in payload.redirects] or None,
            "links": payload.get_metadata("links"),
            "metadata": {k: v for k, v in payload.metadata.items() if k != "links"},
            "last_crawled_at": datetime.now(timezone.utc),
        }
