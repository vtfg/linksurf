from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Middleware, MiddlewareResponse


class ContentTypeMiddleware(Middleware):
    """
    Reads the URL's content type from the response headers.
    """

    async def execute(self, payload: Payload) -> MiddlewareResponse:
        raw = payload.response.headers.get("Content-Type")
        mime_type = raw.split(";")[0].strip() if raw else None

        if mime_type is None:
            return MiddlewareResponse(None, Error("Unknown content type.", retriable=False))

        payload.add_metadata("content_type", mime_type)

        return MiddlewareResponse(payload, None)


class ContentLengthMiddleware(Middleware):
    """
    Reads and parses the URL's content length from the response headers as bytes.
    """

    async def execute(self, payload: Payload) -> MiddlewareResponse:
        raw_length = payload.response.headers.get("Content-Length")

        chunked = "chunked" in payload.response.headers.get("Transfer-Encoding", "").lower()

        if chunked:
            payload.add_metadata("content_length", {"value": None, "chunked": True})

            return MiddlewareResponse(payload, None)

        if raw_length is None:
            payload.add_metadata("content_length", {"value": None, "chunked": False})

            return MiddlewareResponse(payload, None)

        try:
            length = self._parse_length(raw_length)
        except Exception as e:
            return MiddlewareResponse(None, Error("Invalid content length.", retriable=False, exception=e))

        payload.add_metadata("content_length", {"value": length, "chunked": False})

        return MiddlewareResponse(payload, None)

    def _parse_length(self, raw: str) -> int:
        if "," in raw:
            parts = [p.strip() for p in raw.split(",")]

            if len(set(parts)) > 1:
                raise ValueError("Conflicting Content-Length headers")

            value = parts[0]
        else:
            value = raw

        try:
            size = int(value)
        except ValueError:
            raise ValueError(f"Invalid Content-Length format: {value!r}")

        if size < 0:
            raise ValueError("Negative Content-Length")

        return size
