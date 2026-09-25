import asyncio

from linksurf.broker.base import Broker
from linksurf.common.models import URL, Language, Link
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import ConsumerComponent
from linksurf.components.parser.extractors import (
    ExtractorsRegistry,
    ExtractorRules
)
from linksurf.components.parser.extractors.html import (
    AuthorExtractor,
    LinksExtractor,
    MetadataExtractor,
    TextExtractor,
)
from linksurf.components.parser.filters import LanguageFilter
from linksurf.components.parser.middlewares import LanguageMiddleware
from linksurf.logger import Logger
from linksurf.services import Services, BlobStorage, Cache


class Parser(ConsumerComponent):
    NAME = "Parser"
    TOPIC = "url.parse"

    blob_storage: BlobStorage
    cache: Cache

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.middlewares = [
            LanguageMiddleware(),
        ]
        self.filters = [
            LanguageFilter(allowed=[Language.PORTUGUESE]),
        ]

        self.extractors_registry = ExtractorsRegistry()
        self.extractors_registry.register(MetadataExtractor())
        self.extractors_registry.register(LinksExtractor(), callback=self._filter_and_publish_links)
        self.extractors_registry.register(AuthorExtractor())
        self.extractors_registry.register(TextExtractor())

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

        extracted = {}

        extraction_results = await asyncio.to_thread(
            self.extractors_registry.extract,
            payload,
            contents,
        )

        if not extraction_results:
            return Error("No matching extractors for content.", retriable=False)

        for result in extraction_results:
            if result.exception is not None:
                Logger().warning(
                    "component.warning",
                    message=f"Extractor {result.entry.extractor.NAME} failed for {payload.url.address}",
                    exception=str(result.exception),
                )

                continue

            if result.entry.callback:
                await result.entry.callback(payload, result.data)

            extracted[result.entry.extractor.NAME] = result.data

        payload.content.extracted = extracted

        proceed, error = await self.filter(payload)

        # currently the extracted text is only used for language filtering
        # no point in saving to the database
        extracted.pop("text", None)

        payload.content.extracted = extracted

        if error is not None:
            return error

        if not proceed:
            return None

        payload.published = True

        await self.publish("url.store", payload)

        return None

    async def _filter_and_publish_links(self, payload: Payload, links: list[Link]):
        if not isinstance(links, list):
            return

        current_url = payload.url.address

        unique_urls: dict[str, URL] = {}

        for link in links:
            if not isinstance(link, Link):
                continue

            url = URL(link.target)
            normalized_target = url.address

            if normalized_target == current_url:
                continue

            unique_urls.setdefault(normalized_target, url)

        urls = list(unique_urls.values())

        try:
            seen_results = await self.cache.are_urls_seen(urls)
        except Exception as e:
            Logger().warning(
                "component.warning",
                message="Failed to check if urls are seen.",
                exception=str(e),
            )

            return

        links_payloads = [
            Payload(url=url)
            for url, seen in zip(urls, seen_results)
            if not seen
        ]

        if len(links_payloads) > 0:
            await self.publish("url.process", links_payloads)
