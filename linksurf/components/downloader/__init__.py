from linksurf.common.constants import TEN_MEGABYTES_IN_BYTES, MAX_REDIRECT_DEPTH
from linksurf.common.models import HTTPRequest, MimeType, Redirect, URL
from linksurf.common.payload import Content, Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.events.bus import EventBus
from linksurf.services import Services, Fetcher
from linksurf.services.blob import BlobStorage
from linksurf.services.fetcher import MaxRedirectsError


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

    def run(self, payload: Payload) -> Response[Payload | dict[str, Payload]]:
        request = HTTPRequest(url=payload.url.address, follow_redirects=True)

        try:
            response = self.fetcher.http(request)
        except MaxRedirectsError as e:
            return Response(None, Error("Too many redirects.", retriable=False, exception=e))
        except Exception as e:
            return Response(None, Error("HTTP fetch failed.", retriable=True, exception=e))

        if response is None:
            return Response(None, Error("HTTP fetch returned empty response.", retriable=True))

        if response.redirects:
            self._append_redirects(payload, response.redirects)

        if payload.redirects and payload.redirects[-1].depth >= MAX_REDIRECT_DEPTH:
            return Response(None, Error("Redirect depth limit exceeded.", retriable=False))

        # final URL
        final_url = URL(response.url)

        if final_url.domain != payload.url.domain:
            redirect_payload = Payload(url=final_url, redirects=payload.redirects)

            return Response({"url.process": redirect_payload}, None)

        if len(response.body) > TEN_MEGABYTES_IN_BYTES:  # Safety bound
            return Response(None, Error("Body exceeds maximum allowed size.", retriable=False))

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        payload.url = final_url
        key = payload.url.hash

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

    def _append_redirects(self, payload: Payload, redirects: list) -> None:
        # depth needs to be recalculated because the payload can already have an existing redirects fields
        # happens when cross-domain redirect, a new payload gets sent back to the Frontier
        # and Downloader execution stops

        start_depth = len(payload.redirects)

        for i, redirect in enumerate(redirects):
            payload.redirects.append(Redirect(
                source=redirect.source,
                target=redirect.target,
                status_code=redirect.status_code,
                depth=start_depth + i,
            ))
