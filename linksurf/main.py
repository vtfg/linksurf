import random
from enum import Enum
from typing import List
from uuid import uuid4


class Page:
    def __init__(self, url: str, title: str, description: str):
        self.id = uuid4()
        self.url = url
        self.title = title
        self.description = description
        self.noindex = False

    def parse(self):
        print(f"Parsing page {self.url}")

        if self.url == "https://quotes.toscrape.com":
            hyperlinks = ["https://books.toscrape.com"]

            print(f"Found {len(hyperlinks)} hyperlinks")

            for hyperlink in hyperlinks:
                text = "Anchor text goes here"
                nofollow = False  # TODO: Check for link's nofollow directive
                type = LinkType.EXTERNAL  # Only exact hostname should count as internal
                link = Link(source=url, target=hyperlink, type=type, text=text, nofollow=nofollow)

                links.append(link)

                crawl_page(hyperlink)


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


urls: List[str] = []
pages: List[Page] = []
links: List[Link] = []


def can_crawl_page(url: str) -> bool:
    domain = url.split("/")[0]
    robots_url = f"{domain}/robots.txt"

    # TODO: Check robots meta tag

    return random.choice([True, False])


def crawl_page(url: str):
    if not can_crawl_page(url):
        print(f"Skipping {url}")
        return

    print(f"Crawling {url}")

    title = "Title goes here"
    description = "Description goes here"
    page = Page(url=url, title=title, description=description)

    pages.append(page)

    page.parse()


if __name__ == '__main__':
    starting_url = "https://quotes.toscrape.com"

    urls.append(starting_url)

    print(f"Starting crawl with {len(urls)} urls\n")

    for url in urls:
        crawl_page(url)
