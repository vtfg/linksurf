import logging

from linksurf.common.models import URL, Link
from linksurf.common.payload import Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.components.parser.extractors import LinkExtractor
from linksurf.services import Services
from linksurf.services.blob import BlobStorage

logger = logging.getLogger(__name__)


class Parser(Component[Payload]):
    CONSUMES_FROM = "page.parse"
    PRODUCES_TO = ["url.process", "page.store"]

    blob_storage: BlobStorage

    def __init__(self):
        super().__init__()

    def on_start(self, services: Services):
        super().on_start(services)

        self.blob_storage = services.blob_storage

    def run(self, payload: Payload) -> Response[dict]:
        if payload.content is None:
            return Response(None, Error("Payload has no content.", retriable=False))

        if "html" not in payload.content.type:
            return Response(None, Error("Content type not supported.", retriable=False))

        try:
            contents = self.blob_storage.download(payload.content.key)
        except Exception as e:
            logger.exception("Failed to download content for %s", payload.url.address)

            return Response(None, Error("Failed to download content.", retriable=True))

        if contents is None:
            return Response(None, Error("Downloaded content is empty.", retriable=True))

        html = contents.decode(payload.response.encoding)

        links: list[Link] = LinkExtractor.extract(source_url=payload.url, html=html)

        print(f"Extracted {len(links)} links from {payload.url.address}")

        payload.add_metadata("links", [vars(link) for link in links])

        links_payloads = [Payload(url=URL(link.target)) for link in links]

        return Response({
            "url.process": links_payloads,
            "page.store": payload,
        }, None)
