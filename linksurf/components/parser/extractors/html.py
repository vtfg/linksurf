from urllib.parse import urljoin

from bs4 import BeautifulSoup

from linksurf.common.models import MimeType, Link, URL, LinkType
from linksurf.common.payload import Payload
from linksurf.components.parser import ExtractorRules
from linksurf.components.parser.extractors import Extractor


class MetadataExtractor(Extractor):
    NAME = "metadata"
    RULES = ExtractorRules(mime_types=[MimeType.HTML])

    def extract(self, payload: Payload, contents: bytes) -> dict[str, str | list]:
        if payload.response is None:
            raise Exception("Payload doesn't contain a response.")

        html = contents.decode(payload.response.encoding)

        soup = BeautifulSoup(html, "html.parser")

        html_tag = soup.find("html")
        language = html_tag.attrs.get("lang") or None

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        base_tag = soup.select_one("head > base[href]")
        base = base_tag.get("href").strip() if base_tag else None

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
    RULES = ExtractorRules(mime_types=[MimeType.HTML], domain="quotes.toscrape.com", path_pattern=r"^/author/")

    def extract(self, payload: Payload, contents: bytes) -> dict[str, str | None]:
        if payload.response is None:
            raise Exception("Payload doesn't contain a response.")

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
    RULES = ExtractorRules(mime_types=[MimeType.HTML])

    def extract(self, payload: Payload, contents: bytes) -> list[Link]:
        html = contents.decode(payload.response.encoding)

        soup = BeautifulSoup(html, "html.parser")

        page_url = payload.url

        base_url = page_url.address

        base_tag = soup.select_one("head > base[href]")

        if base_tag:
            # base href may be relative
            resolved_base = urljoin(page_url.address, base_tag.get("href").strip())
            resolved_base_url = URL(resolved_base)

            if resolved_base_url.scheme in ("http", "https") and resolved_base_url.domain:
                base_url = resolved_base

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
                raw_target=href,
                type=link_type,
                text=a.get_text(strip=True) or None,
                rel=rel,
            ))

        return links
