from linksurf.common.models import URL, MimeType, Link
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import LinksExtractor, MetadataExtractor, Extractor
from linksurf.logger import Logger
from linksurf.services import Services
from linksurf.services.blob import BlobStorage


class Parser(Component):
    TOPIC = "url.parse"

    blob_storage: BlobStorage

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

        match payload.content.type:
            case MimeType.HTML:
                try:
                    html = contents.decode(payload.response.encoding)

                    metadata = MetadataExtractor.extract(page_url=payload.url, html=html)
                    links = LinksExtractor.extract(page_url=payload.url, html=html)

                    payload.content.extracted = {"metadata": metadata, "links": links}

                    Logger().debug("component.debug",
                                   message=f"Extracted {len(links)} links from {payload.url.address}")

                    self._filter_and_publish_links(payload, links)

                except Exception as e:
                    return Error("Content extraction failed.", exception=e, retriable=False)
            case _:
                return Error("Content type not supported.", retriable=False)

        self.publish("url.store", payload)

        return None

    def _filter_and_publish_links(self, payload: Payload, links: list[Link]):
        page_url = payload.url.address

        for link in links:
            target_url = URL(link.target)

            if target_url.address == page_url:
                continue

            link_payload = Payload(url=target_url)

            self.publish("url.process", link_payload)
