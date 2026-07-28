import asyncio

from langdetect import detect, LangDetectException

from linksurf.common.payload import Payload
from linksurf.components.base import Middleware, MiddlewareResponse

TEXT_SAMPLE_MAX_CHARS = 2000


class LanguageMiddleware(Middleware):
    """
    Detects the content's language. Checks the extracted metadata language attribute first,
    falls back to text-based detection using `langdetect`.

    Must run after the Parser's extraction, since it depends on payload.content.extracted.
    """

    async def execute(self, payload: Payload) -> MiddlewareResponse:
        extracted = payload.content.extracted if payload.content else None

        if not extracted:
            payload.add_metadata("language", None)

            return MiddlewareResponse(payload, None)

        code = self._from_html_attribute(extracted)

        if code is None:
            code = await asyncio.to_thread(self._from_text, extracted)

        payload.add_metadata("language", code)

        return MiddlewareResponse(payload, None)

    def _from_html_attribute(self, extracted: dict) -> str | None:
        metadata = extracted.get("metadata") or {}
        lang = metadata.get("language")

        if not lang:
            return None

        # take the primary subtag: "pt-BR" -> "pt", "en_US" -> "en"
        primary = lang.strip().lower().replace("_", "-").split("-")[0]

        return primary or None

    def _from_text(self, extracted: dict) -> str | None:
        text = extracted.get("text")

        if not text:
            return None

        try:
            return detect(text[:TEXT_SAMPLE_MAX_CHARS])
        except LangDetectException:
            return None
