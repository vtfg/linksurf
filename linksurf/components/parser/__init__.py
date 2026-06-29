from linksurf.common.models import URL, Link, MimeType
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import LinkExtractor
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

        if payload.content.type != MimeType.HTML:
            return Error("Content type not supported.", retriable=False)

        try:
            contents = self.blob_storage.download(payload.content.key)
        except Exception as e:
            return Error("Blob download failed.", retriable=True, exception=e)

        if contents is None:
            return Error("Blob downloaded content is empty.", retriable=False)

        html = contents.decode(payload.response.encoding)

        links: list[Link] = LinkExtractor.extract(source_url=payload.url, html=html)

        Logger().debug("component.debug", message=f"Extracted {len(links)} links from {payload.url.address}")

        payload.add_metadata("links", [vars(link) for link in links])

        links_payloads = [Payload(url=URL(link.target)) for link in links]

        self.publish("url.process", links_payloads)

        self.publish("url.store", payload)

        return None
