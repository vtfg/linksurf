from dataclasses import asdict
from datetime import datetime, timezone

from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.components.base import Component, Filter
from linksurf.events.bus import EventBus
from linksurf.services import Services
from linksurf.services.database import Database


class Storage(Component[Payload]):
    CONSUMES_FROM = "page.store"

    database: Database

    def __init__(self):
        super().__init__()

        self.filters: list[Filter] = []

    def on_start(self, settings: Settings, services: Services, event_bus: EventBus):
        super().on_start(settings, services, event_bus)

        self.database = services.database

    def run(self, payload: Payload) -> Response[Payload]:
        if payload.content is None:
            return Response(None, Error("Payload has no content.", retriable=False))

        data = self._build_data(payload)

        try:
            storage_id = self.database.save_url(data)
        except Exception as e:
            return Response(None, Error("Database write failed.", retriable=True, exception=e))

        payload.storage_id = storage_id

        return Response(payload, None)

    def _build_data(self, payload: Payload) -> dict:
        return {
            "address": payload.url.address,
            "hash": payload.url.hash,
            "domain": payload.url.domain,
            "request": asdict(payload.request) if payload.request else None,
            "response": asdict(payload.response) if payload.response else None,
            "content": asdict(payload.content) if payload.content else None,
            "links": payload.get_metadata("links"),
            "metadata": {k: v for k, v in payload.metadata.items() if k != "links"},
            "last_crawled_at": datetime.now(timezone.utc),
        }
