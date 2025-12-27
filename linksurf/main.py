from enum import Enum
from typing import List
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4

import requests
from dotenv import load_dotenv

from linksurf.utils import get_env

load_dotenv()

proxy_http = get_env("PROXY_HTTP_URL")
proxy_https = get_env("PROXY_HTTPS_URL")
user_agent = get_env("USER_AGENT")


class Fetcher:
    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> requests.Response:
        split = urlsplit(self.url)

        if split.scheme in ["http", "https"]:
            return self._http()
        else:
            raise NotImplementedError()

    def _http(self) -> requests.Response:
        headers = {
            "User-Agent": user_agent,
        }

        proxies = {
            "http": proxy_http,
            "https": proxy_https,
        }

        return requests.get(self.url, headers=headers, proxies=proxies)


class URL:
    def __init__(self, address: str, depth: int = 1):
        self.address = address
        self.depth = depth
        self.status = URLStatus.PENDING

    def get_base_domain(self):
        parts = urlsplit(self.address)
        return f"{parts.scheme}://{parts.netloc}"


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
        if url.address == address and url.status == URLStatus.CRAWLED:
            return True

    return False


def can_crawl_page(domain: str, address: str) -> bool:
    robots_url = f"{domain}/robots.txt"

    print(f"Checking permissions for {domain}")

    fetcher = Fetcher(robots_url)
    response = fetcher.fetch()

    if response.status_code != 200:
        return True

    if not response.text:
        return True

    if not "text/plain" in response.headers["Content-Type"].lower():
        return True

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())

    return parser.can_fetch("*", address)


def crawl(address: str, depth: int = 1, max_depth: int = 4):
    url = URL(address=address, depth=depth)

    if is_page_already_crawled(url.address):
        print(f"Skipping {url.address}: already crawled")

        return

    if not can_crawl_page(url.get_base_domain(), url.address):
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

    url.status = URLStatus.CRAWLED

    for link in page.links:
        crawl(link.target, depth + 1)


if __name__ == '__main__':
    seed = ["https://quotes.toscrape.com"]

    print(f"Starting crawl with {len(seed)} urls\n")

    for url in seed:
        crawl(url)

    print(f"\nFinished crawl with {len(urls)} urls")

    for index, url in enumerate(urls):
        print(f"[{index}]: {url.address=} {url.status=} {url.depth=}")
