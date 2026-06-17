from linksurf.common.models import URL, Link, MimeType
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import LinkExtractor
from linksurf.events.bus import EventBus
from linksurf.logger import Logger
from linksurf.services import Services
from linksurf.services.blob import BlobStorage


class Parser(Component[Payload]):
    CONSUMES_FROM = "page.parse"
    PRODUCES_TO = ["page.store", "url.process"]

    blob_storage: BlobStorage

    def __init__(self):
        super().__init__()

    def on_start(self, settings: Settings, services: Services, event_bus: EventBus):
        super().on_start(settings, services, event_bus)

        self.blob_storage = services.blob_storage

    def run(self, payload: Payload) -> Response[dict]:
        if payload.content is None:
            return Response(None, Error("Payload has no content.", retriable=False))

        if payload.content.type != MimeType.HTML:
            return Response(None, Error("Content type not supported.", retriable=False))

        try:
            contents = self.blob_storage.download(payload.content.key)
        except Exception as e:
            return Response(None, Error("Blob download failed.", retriable=True, exception=e))

        if contents is None:
            return Response(None, Error("Blob downloaded content is empty.", retriable=False))

        html = contents.decode(payload.response.encoding)

        links: list[Link] = LinkExtractor.extract(source_url=payload.url, html=html)

        Logger().debug("component.debug", message=f"Extracted {len(links)} links from {payload.url.address}")

        payload.add_metadata("links", [vars(link) for link in links])

        links_payloads = [Payload(url=URL(link.target)) for link in links]

        return Response({
            "page.store": payload,
            "url.process": links_payloads,
        }, None)
