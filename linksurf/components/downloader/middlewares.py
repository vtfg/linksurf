import logging

from linksurf.common.models import HTTPRequest
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse
from linksurf.services import Fetcher

logger = logging.getLogger(__name__)


class ContentTypeMiddleware(Middleware):
    """
    Retrieves the URL's content type from the response headers.
    """

    fetcher: Fetcher

    def on_start(self, services):
        self.fetcher = services.fetcher

    def execute(self, payload: Payload) -> MiddlewareResponse:
        url = payload.url.address

        request = HTTPRequest(url, method="HEAD")

        try:
            response = self.fetcher.http(request)
        except Exception as e:
            logger.exception("Fetcher raised an exception for %s", url)

            return MiddlewareResponse(None, Error("Fetch failed.", retriable=True))

        mime_type = response.content_type.split(";")[0].strip() if response.content_type else None

        if mime_type is None:
            return MiddlewareResponse(None, Error("Unknown content type.", retriable=True))

        payload.add_metadata("content_type", mime_type)

        return MiddlewareResponse(payload, None)
