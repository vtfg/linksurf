from linksurf.common.models import Language
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Filter, FilterResponse
from linksurf.components.parser.middlewares import LanguageMiddleware
from linksurf.services import Database, Services


class LanguageFilter(Filter):
    """
    Basic language filter that uses the code returned from the LanguageMiddleware.

    Records the language metric to the domain's Database record.
    """

    DEPENDS_ON = [LanguageMiddleware]

    database: Database

    def __init__(self, allowed: list[Language]):
        self.allowed = allowed

    async def on_start(self, settings: Settings, services: Services):
        self.database = services.database

    async def execute(self, payload: Payload) -> FilterResponse:
        code = payload.get_metadata("language")

        try:
            language = Language(code)
        except ValueError:
            language = None

        if language is not None:
            try:
                await self.database.record_language(payload.url.domain, language.value,
                                                    allowed=language in self.allowed)
            except Exception as e:
                return FilterResponse(False, Error("Failed to record language metric.", retriable=True, exception=e))

        return FilterResponse(language in self.allowed, None)
