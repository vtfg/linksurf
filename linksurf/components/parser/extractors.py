from urllib.parse import urljoin

from bs4 import BeautifulSoup

from linksurf.common.models import Link, LinkType, URL


class LinkExtractor:
    @staticmethod
    def extract(source_url: URL, html: str) -> list[Link]:
        soup = BeautifulSoup(html, "html.parser")

        links: list[Link] = []

        for a in soup.find_all("a"):
            href = a.get("href")

            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue

            target = urljoin(source_url.address, href)

            target_url = URL(target)

            if not source_url.domain or not target_url.domain:
                continue

            source_domain = source_url.domain
            target_domain = target_url.domain

            link_type = LinkType.INTERNAL if source_domain == target_domain else LinkType.EXTERNAL

            rel = a.get("rel") or None

            links.append(Link(
                source=source_url.address,
                target=target,
                type=link_type,
                text=a.get_text(strip=True) or None,
                rel=rel,
            ))

        return links
