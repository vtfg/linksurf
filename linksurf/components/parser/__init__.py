import asyncio

from linksurf.broker.base import Broker
from linksurf.common.models import URL, Link
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import (
    ExtractorsRegistry,
    ExtractorRules
)
from linksurf.components.parser.extractors.html import MetadataExtractor, LinksExtractor, AuthorExtractor
from linksurf.logger import Logger
from linksurf.services import Services, BlobStorage, Cache


class Parser(Component):
    TOPIC = "url.parse"

    blob_storage: BlobStorage
    cache: Cache

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.extractors_registry = ExtractorsRegistry()
        self.extractors_registry.register(MetadataExtractor())
        self.extractors_registry.register(LinksExtractor(), callback=self._filter_and_publish_links)
        self.extractors_registry.register(AuthorExtractor())

    async def on_start(self, settings: Settings, services: Services):
        await super().on_start(settings, services)

        self.blob_storage = services.blob_storage
        self.cache = services.cache

        await self.subscribe(self.TOPIC, self.parse, concurrency=10)

    async def parse(self, payload: Payload) -> Error | None:
        if payload.content is None:
            return Error("Payload has no content.", retriable=False)

        try:
            contents = await self.blob_storage.download(payload.content.key)
        except Exception as e:
            return Error("Blob download failed.", retriable=True, exception=e)

        if contents is None:
            return Error("Blob downloaded content is empty.", retriable=False)

        matching_extractors = self.extractors_registry.match(payload.content.type, payload.url)

        if len(matching_extractors) == 0:
            return Error("Content type not supported.", retriable=False)

        extracted = {}

        for entry in matching_extractors:
            try:
                data = await asyncio.to_thread(entry.extractor.extract, payload, contents)

                if entry.callback:
                    await entry.callback(payload, data)
            except Exception as e:
                Logger().warning(
                    "component.warning",
                    message=f"Extractor {entry.extractor.NAME} failed for {payload.url.address}",
                    exception=str(e),
                )

                continue

            extracted[entry.extractor.NAME] = data

        payload.content.extracted = extracted

        await self.publish("url.store", payload)

        return None

    async def _filter_and_publish_links(self, payload: Payload, links: list[Link]):
        if not isinstance(links, list):
            return

        current_url = payload.url.address

        unique_links: set[str] = set()

        for link in links:
            if not isinstance(link, Link):
                continue

            if link.target == current_url:
                continue

            url = URL(link.target)

            try:
                seen = await self.cache.is_url_seen(url)
            except Exception as e:
                Logger().warning(
                    "component.warning",
                    message="Failed to check if url is seen.",
                    exception=str(e),
                )

                continue

            if not seen:
                unique_links.add(link.target)

        links_payloads = [Payload(url=URL(link)) for link in unique_links]

        if len(links_payloads) > 0:
            await self.publish("url.process", links_payloads)
