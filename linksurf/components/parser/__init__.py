from linksurf.broker.base import Broker
from linksurf.common.models import URL, MimeType, Link
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import (
    ExtractorsRegistry,
    ExtractorRules,
    LinksExtractor,
    MetadataExtractor,
    AuthorExtractor,
)
from linksurf.logger import Logger
from linksurf.services import Services
from linksurf.services.blob import BlobStorage


class Parser(Component):
    TOPIC = "url.parse"

    blob_storage: BlobStorage

    def __init__(self, broker: Broker):
        super().__init__(broker)

        self.extractors_registry = ExtractorsRegistry()
        self.extractors_registry.register(MetadataExtractor(), ExtractorRules(mime_types=[MimeType.HTML]))
        self.extractors_registry.register(
            LinksExtractor(),
            ExtractorRules(mime_types=[MimeType.HTML]),
            callback=self._filter_and_publish_links
        )
        self.extractors_registry.register(
            AuthorExtractor(),
            ExtractorRules(mime_types=[MimeType.HTML], domain="quotes.toscrape.com", path_pattern=r"^/author/"),
        )

    def on_start(self, settings: Settings, services: Services):
        super().on_start(settings, services)

        self.blob_storage = services.blob_storage

        self.subscribe(self.TOPIC, self.parse)

    def parse(self, payload: Payload) -> Error | None:
        if payload.content is None:
            return Error("Payload has no content.", retriable=False)

        try:
            contents = self.blob_storage.download(payload.content.key)
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
                data = entry.extractor.extract(payload, contents)

                if entry.callback:
                    entry.callback(payload, data)
            except Exception as e:
                Logger().warning(
                    "component.warning",
                    message=f"Extractor {entry.extractor.NAME} failed for {payload.url.address}",
                    exception=str(e),
                )

                continue

            extracted[entry.extractor.NAME] = data

        payload.content.extracted = extracted

        self.publish("url.store", payload)

        return None

    def _filter_and_publish_links(self, payload: Payload, links: list[Link]):
        current_url = payload.url.address

        unique_links: set[str] = set()

        for link in links:
            if link.target == current_url:
                continue

            unique_links.add(link.target)

        links_payloads = [Payload(url=URL(link)) for link in unique_links]

        self.publish("url.process", links_payloads)
