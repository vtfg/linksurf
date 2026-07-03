from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from linksurf.common.models import Link, LinkType, URL


class Extractor:
    NAME: str

    @staticmethod
    def extract(page_url: URL, html: str) -> Any:
        pass


class MetadataExtractor(Extractor):
    NAME = "metadata"

    @staticmethod
    def extract(page_url: URL, html: str) -> dict[str, str | list]:
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


class LinksExtractor(Extractor):
    NAME = "links"

    @staticmethod
    def extract(page_url: URL, html: str) -> list[Link]:
        soup = BeautifulSoup(html, "html.parser")

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
