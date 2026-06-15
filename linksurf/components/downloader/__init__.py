from linksurf.common.constants import TEN_MEGABYTES_IN_BYTES
from linksurf.common.models import HTTPRequest, MimeType
from linksurf.common.payload import Content, Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.events.bus import EventBus
from linksurf.services import Services, Fetcher
from linksurf.services.blob import BlobStorage


class Downloader(Component[Payload]):
    CONSUMES_FROM = "url.fetch"
    PRODUCES_TO = "page.parse"

    fetcher: Fetcher
    blob_storage: BlobStorage

    def __init__(self):
        super().__init__()

    def on_start(self, settings: Settings, services: Services, event_bus: EventBus):
        super().on_start(settings, services, event_bus)

        self.fetcher = services.fetcher
        self.blob_storage = services.blob_storage

    def run(self, payload: Payload) -> Response[Payload]:
        url = payload.url

        request = HTTPRequest(url=url.address)

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            return Response(None, Error("HTTP fetch failed.", retriable=True, exception=e))

        if response is None:
            return Response(None, Error("HTTP fetch returned empty response.", retriable=True))

        if len(response.body) > TEN_MEGABYTES_IN_BYTES:  # Safety bound
            return Response(None, Error("Body exceeds maximum allowed size.", retriable=False))

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        key = url.hash

        try:
            self.blob_storage.upload(response.body, key, content_type=mime_type)
        except Exception as e:
            return Response(None, Error("Blob upload failed.", retriable=True, exception=e))

        try:
            type = MimeType(mime_type)
        except ValueError:
            type = MimeType.UNKNOWN

        payload.content = Content(key=key, type=type)
        payload.request = request.to_summary()
        payload.response = response.to_summary()

        return Response(payload, None)
