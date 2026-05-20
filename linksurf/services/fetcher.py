from linksurf.common.models import HTTPRequest, HTTPResponse
from linksurf.services.base import Service


class Fetcher(Service):
    NAME = "fetcher"

    def http(self, request: HTTPRequest) -> HTTPResponse:
        pass