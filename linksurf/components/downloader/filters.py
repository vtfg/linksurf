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
