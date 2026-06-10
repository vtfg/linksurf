from linksurf.common.constants import TEN_MEGABYTES_IN_BYTES
from linksurf.common.models import MimeType
from linksurf.common.payload import Payload
from linksurf.components.base import Filter, FilterResponse


class ContentTypeFilter(Filter):
    def __init__(self, allowed: list[MimeType]):
        self.allowed = allowed

    def execute(self, payload: Payload) -> FilterResponse:
        type = payload.get_metadata("content_type")

        if type not in self.allowed:
            return FilterResponse(False, None)

        return FilterResponse(True, None)


class ContentLengthFilter(Filter):
    def __init__(self, max_bytes: int = TEN_MEGABYTES_IN_BYTES):
        if max_bytes > TEN_MEGABYTES_IN_BYTES:
            raise ValueError(f"Defined maximum content length is higher than allowed (10MB).")

        self.max_bytes = max_bytes

    def execute(self, payload: Payload) -> FilterResponse:
        content_length = payload.get_metadata("content_length") or {}

        value = content_length.get("value")

        if value is not None and value > self.max_bytes:
            return FilterResponse(False, None)

        return FilterResponse(True, None)
