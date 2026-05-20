from linksurf.common.models import URL, HTTPResponse, HTTPRequest
from linksurf.common.types import Response, Error
from linksurf.components.base import Component
from linksurf.services import Services, Fetcher


class Downloader(Component[HTTPResponse]):
    CONSUMES_FROM = "urls"
    PRODUCES_TO = "files"

    fetcher: Fetcher

    def __init__(self):
        super().__init__()

    def on_start(self, services: Services):
        self.fetcher = services.fetcher

    def process(self, url: URL) -> Response[HTTPResponse]:
        request = HTTPRequest()

        if url.scheme in ["http", "https"]:
            return Response(self.fetcher.http(request), None)

        return Response(None, Error("Schema not supported", retriable=False))

    def _http(self, url: URL) -> HTTPResponse:
        return HTTPResponse()
