from linksurf.common.models import HTTPRequest, HTTPResponse, URL
from linksurf.common.payload import Payload
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.services import Services, Fetcher


class Downloader(Component[Payload]):
    CONSUMES_FROM = "url.fetch"
    PRODUCES_TO = "page.parse"

    fetcher: Fetcher

    def __init__(self):
        super().__init__()

    def on_start(self, services: Services):
        self.fetcher = services.fetcher

    def run(self, payload: Payload) -> Response[Payload]:
        request = HTTPRequest()

        if payload.url.scheme in ["http", "https"]:
            http_response = self.fetcher.http(request)

            return Response(payload, None)

        return Response(None, Error("Schema not supported", retriable=False))

    def _http(self, url: URL) -> HTTPResponse:
        return HTTPResponse()
