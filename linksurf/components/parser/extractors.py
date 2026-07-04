import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from linksurf.common.models import Link, LinkType, URL, MimeType
from linksurf.common.payload import Payload


class Extractor:
    NAME: str

    def extract(self, payload: Payload, contents: bytes) -> Any:
        pass


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


type ExtractorCallback = Callable[[Payload, Any], None]


@dataclass(frozen=True)
class ExtractorEntry:
    extractor: Extractor
    rules: ExtractorRules = field(default_factory=ExtractorRules)
    callback: ExtractorCallback | None = None


class ExtractorsRegistry:
    def __init__(self):
        self._entries: list[ExtractorEntry] = []

    def register(self, extractor: Extractor, rules: ExtractorRules = ExtractorRules(),
                 callback: ExtractorCallback | None = None) -> None:
        self._entries.append(ExtractorEntry(extractor, rules, callback))

    def match(self, mime_type: MimeType, url: URL) -> list[ExtractorEntry]:
        return [entry for entry in self._entries if entry.rules.matches(mime_type, url)]


class MetadataExtractor(Extractor):
    NAME = "metadata"

    def extract(self, payload: Payload, contents: bytes) -> dict[str, str | list]:
        html = contents.decode(payload.response.encoding)

        soup = BeautifulSoup(html, "html.parser")

        html_tag = soup.find("html")
        language = html_tag.attrs.get("lang") or None

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        base_tag = soup.select_one("head > base")
        base = base_tag.get("href") if base_tag else None

        metas = {}
        opengraph = {}
        article = {}

        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")

            if name and content:
                if name.startswith("og:"):
                    opengraph[name] = content
                elif name.startswith("article:"):
                    article[name] = content
                else:
                    metas[name] = content

        description = metas.get("description")
        keywords = metas.get("keywords")
        robots = metas.get("robots")

        return {
            "base": base,
            "title": title,
            "description": description,
            "language": language,
            "keywords": keywords,
            "robots": robots,
            "opengraph": opengraph or None,
            "article": article or None,
        }


class AuthorExtractor(Extractor):
    NAME = "author"

    def extract(self, payload: Payload, contents: bytes) -> dict[str, str | None]:
        html = contents.decode(payload.response.encoding)

        soup = BeautifulSoup(html, "html.parser")

        details = soup.select_one(".author-details")

        name_tag = details.select_one(".author-title") if details else None
        description_tag = details.select_one(".author-description") if details else None

        name = name_tag.get_text(strip=True) if name_tag else None
        description = description_tag.get_text(strip=True) if description_tag else None

        return {"name": name, "description": description}


class LinksExtractor(Extractor):
    NAME = "links"

    def extract(self, payload: Payload, contents: bytes) -> list[Link]:
        html = contents.decode(payload.response.encoding)

        soup = BeautifulSoup(html, "html.parser")

        page_url = payload.url

        base_url = page_url.address

        base_tag = soup.select_one("head > base")

        if base_tag:
            base_tag_href = base_tag.get("href")

            if base_tag_href:
                # TODO: Validate URL (using pip package "validators"?)

                base_url = base_tag_href.strip()

        links: list[Link] = []

        for a in soup.find_all("a"):
            href = a.get("href")

            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue

            target = urljoin(base_url, href)

            target_url = URL(target)

            if not page_url.domain or not target_url.domain:
                continue

            source_domain = page_url.domain
            target_domain = target_url.domain

            link_type = LinkType.INTERNAL if source_domain == target_domain else LinkType.EXTERNAL

            rel = a.get("rel") or None

            links.append(Link(
                source=page_url.address,
                target=target,
                type=link_type,
                text=a.get_text(strip=True) or None,
                rel=rel,
            ))

        return links
