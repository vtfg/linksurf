import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from bs4 import BeautifulSoup

from linksurf.common.models import URL, MimeType
from linksurf.common.payload import Payload


@dataclass
class ExtractorRules:
    mime_types: list[MimeType] | None = None  # None = matches any mime type
    domain: str | None = None  # None = matches any domain; exact match, no subdomain matching
    path_pattern: str | None = None  # None = matches any path; regex applied to URL.path

    def __post_init__(self) -> None:
        self._mime_types_set = set(self.mime_types) if self.mime_types else None
        self._path_pattern_regex = re.compile(self.path_pattern) if self.path_pattern else None

    def matches(self, mime_type: MimeType, url: URL) -> bool:
        if self._mime_types_set is not None and mime_type not in self._mime_types_set:
            return False

        if self.domain is not None and url.domain != self.domain:
            return False

        if self._path_pattern_regex is not None and not self._path_pattern_regex.search(url.path):
            return False

        return True


type ExtractorCallback = Callable[[Payload, Any], Awaitable[None]]


class Extractor:
    NAME: str
    RULES: ExtractorRules

    def extract(self, payload: Payload, source: Any, /) -> Any:
        raise NotImplementedError()


class HTMLExtractor(Extractor):
    def extract(self, payload: Payload, document: BeautifulSoup, /) -> Any:
        raise NotImplementedError()


@dataclass(frozen=True)
class ExtractorEntry:
    extractor: Extractor
    rules: ExtractorRules = field(default_factory=ExtractorRules)
    callback: ExtractorCallback | None = None


@dataclass(frozen=True)
class ExtractorResult:
    entry: ExtractorEntry
    data: Any = None
    exception: Exception | None = None


class ExtractorsRegistry:
    def __init__(self):
        self._entries: list[ExtractorEntry] = []

    def register(self, extractor: Extractor, callback: ExtractorCallback | None = None) -> None:
        self._entries.append(ExtractorEntry(extractor, extractor.RULES, callback))

    def match(self, mime_type: MimeType, url: URL) -> list[ExtractorEntry]:
        return [entry for entry in self._entries if entry.rules.matches(mime_type, url)]

    def extract(self, payload: Payload, contents: bytes, /) -> list[ExtractorResult]:
        if payload.content is None:
            return []

        entries = self.match(payload.content.type, payload.url)

        if not entries:
            return []

        html_document = None

        if any(isinstance(entry.extractor, HTMLExtractor) for entry in entries):
            try:
                html_document = self._build_html_document(payload, contents)
            except Exception as exception:
                return [ExtractorResult(entry, exception=exception) for entry in entries]

        results: list[ExtractorResult] = []

        for entry in entries:
            source = html_document if isinstance(entry.extractor, HTMLExtractor) else contents

            try:
                data = entry.extractor.extract(payload, source)

                results.append(ExtractorResult(entry, data=data))
            except Exception as exception:
                results.append(ExtractorResult(entry, exception=exception))

        return results

    def _build_html_document(self, payload: Payload, contents: bytes) -> BeautifulSoup:
        if payload.response is None:
            raise ValueError("Payload doesn't contain a response.")

        html = contents.decode(payload.response.encoding or "utf-8")

        return BeautifulSoup(html, "html.parser")
