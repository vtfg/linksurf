from linksurf.common.models import Language
from linksurf.common.payload import Payload
from linksurf.components.base import Filter, FilterResponse
from linksurf.components.parser.middlewares import LanguageMiddleware


class LanguageFilter(Filter):
    DEPENDS_ON = [LanguageMiddleware]

    def __init__(self, allowed: list[Language]):
        self.allowed = allowed

    async def execute(self, payload: Payload) -> FilterResponse:
        code = payload.get_metadata("language")

        try:
            language = Language(code)
        except ValueError:
            language = None

        return FilterResponse(language in self.allowed, None)
