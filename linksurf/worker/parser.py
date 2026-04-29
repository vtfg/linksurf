from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from linksurf.models import Link, LinkType, Metadata, MetaTag


class HTMLParser:
    @staticmethod
    def parse(page_url: str, html: str) -> tuple[Metadata, list[Link]]:
        metadata = MetadataExtractor.extract(html)
        links = LinkExtractor.extract(page_url, html)
        return metadata, links


class LinkExtractor:
    @staticmethod
    def extract(page_url: str, html: str) -> list[Link]:
        soup = BeautifulSoup(html, "html.parser")
        links = []

        for a in soup.find_all("a"):
            href = a.get("href")

            if not href:
                continue

            target = urljoin(page_url, href)

            source_hostname = urlsplit(page_url).hostname
            target_hostname = urlsplit(target).hostname

            if not source_hostname or not target_hostname:
                continue

            source_domain = source_hostname.removeprefix("www.")
            target_domain = target_hostname.removeprefix("www.")

            link_type = LinkType.INTERNAL if source_domain == target_domain else LinkType.EXTERNAL
            rel = a.get("rel") or []
            nofollow = "nofollow" in rel

            links.append(Link(
                source=page_url,
                target=target,
                type=link_type,
                text=a.string,
                nofollow=nofollow,
            ))

        return links


class MetadataExtractor:
    @staticmethod
    def extract(html: str) -> Metadata:
        soup = BeautifulSoup(html, "html.parser")

        html_tag = soup.find("html")
        lang = html_tag.get("lang") if html_tag else None

        title_tag = soup.find("title")
        title = title_tag.string if title_tag else None

        tags = []
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                tags.append(MetaTag(name=name, content=content))

        description = next((t.content for t in tags if t.name == "description"), None)

        return Metadata(title=title, description=description, lang=lang, tags=tags)
