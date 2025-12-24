import random
from enum import Enum
from typing import List
from uuid import uuid4


class URL:
    def __init__(self, address: str, depth: int = 1):
        self.address = address
        self.depth = depth
        self.status = URLStatus.PENDING


class URLStatus(Enum):
    PENDING = 1
    CRAWLED = 2
    FAILED = 3
    SKIPPED = 4


class Page:
    def __init__(self, url: str, title: str, description: str):
        self.id = uuid4()
        self.url = url
        self.title = title
        self.description = description
        self.noindex = False
        self.links: List[Link] = []

    def parse(self):
        print(f"Parsing page {self.url}")

        found_links = [
            Link(source=self.url, target="https://books.toscrape.com", type=LinkType.EXTERNAL,
                 text="Anchor text goes here", nofollow=False)
        ]

        print(f"Found {len(found_links)} hyperlinks")

        self.links.extend(found_links)
        links.extend(found_links)

        print(f"Finished parsing page {self.url}")


class Link:
    def __init__(self, source: str, target: str, type: LinkType, text: str, nofollow: bool = False):
        self.id = uuid4()
        self.source = source
        self.target = target
        self.type = type
        self.text = text
        self.nofollow = nofollow


class LinkType(Enum):
    INTERNAL = 1
    EXTERNAL = 2


urls: List[URL] = []
pages: List[Page] = []
links: List[Link] = []


def is_page_already_crawled(address: str) -> bool:
    for url in urls:
        if url.address == address:
            return True

    return False


def can_crawl_page(address: str) -> bool:
    domain = address.split("/")[0]
    robots_url = f"{domain}/robots.txt"

    # TODO: Check robots meta tag

    return random.choice([True, False])


def crawl(address: str, depth: int = 1, max_depth: int = 4):
    url = URL(address=address, depth=depth)

    if is_page_already_crawled(url.address):
        print(f"Skipping {url.address}: already crawled")

        return

    if not can_crawl_page(url.address):
        print(f"Skipping {url.address}: not allowed")

        return

    if depth > max_depth:
        print(f"Skipping {url.address}: reached max depth")

        url.status = URLStatus.SKIPPED

    # TODO: Check if url was skipped before, change depth if lower and crawl

    urls.append(url)

    if url.status == URLStatus.SKIPPED:
        return

    print(f"Crawling {url.address}")

    title = "Title goes here"
    description = "Description goes here"
    page = Page(url=url.address, title=title, description=description)

    pages.append(page)

    page.parse()

    for link in page.links:
        crawl(link.target, depth + 1)

    url.status = URLStatus.CRAWLED


if __name__ == '__main__':
    seed = ["https://quotes.toscrape.com"]

    print(f"Starting crawl with {len(seed)} urls\n")

    for url in seed:
        crawl(url)

    print(f"\nFinished crawl with {len(urls)} urls")

    for index, url in enumerate(urls):
        print(f"[{index}]: {url.address=} {url.status=} {url.depth=}")
