import logging

from linksurf.common.models import HTTPRequest, MimeType
from linksurf.common.payload import Content, Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.services import Services, Fetcher
from linksurf.services.blob import BlobStorage

logger = logging.getLogger(__name__)


class Downloader(Component[Payload]):
    CONSUMES_FROM = "url.fetch"
    PRODUCES_TO = "page.parse"

    fetcher: Fetcher
    blob_storage: BlobStorage

    def __init__(self):
        super().__init__()

    def on_start(self, services: Services):
        super().on_start(services)

        self.fetcher = services.fetcher
        self.blob_storage = services.blob_storage

    def run(self, payload: Payload) -> Response[Payload]:
        url = payload.url

        if url.scheme not in ["http", "https"]:
            return Response(None, Error("Schema not supported", retriable=False))

        request = HTTPRequest(url=url.address)

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", url.address)

            return Response(None, Error("Fetch failed.", retriable=True))

        if response is None:
            return Response(None, Error("Fetcher returned no response.", retriable=True))

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        key = url.hash

        try:
            self.blob_storage.upload(response.body, key, content_type=mime_type)
        except Exception as e:
            logger.exception("Blob upload failed for %s", url.address)

            return Response(None, Error("Blob upload failed.", retriable=True))

        try:
            type = MimeType(mime_type)
        except ValueError:
            logger.exception("Mime type not supported: %s", mime_type)

            type = MimeType.UNKNOWN

        payload.content = Content(key=key, type=type)
        payload.request = request.to_summary()
        payload.response = response.to_summary()

        return Response(payload, None)
