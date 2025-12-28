import json
from datetime import datetime
from enum import Enum
from typing import List
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
from uuid import uuid4, UUID

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from linksurf.utils import get_env, get_base_domain

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


class RobotsCache:
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.cache: dict[str, RobotFileParser] = {}

    def get_parser(self, url: str) -> RobotFileParser | None:
        domain = get_base_domain(url)

        if domain in self.cache:
            print(f"Using cached robots for {domain}")

            return self.cache[domain]

        print(f"Fetching robots for {domain}")

        robots_url = f"{domain}/robots.txt"

        fetcher = Fetcher(robots_url)
        response = fetcher.fetch()

        parser = RobotFileParser()

        lines = []

        if response.status_code == 200 and "text/plain" in response.headers["Content-Type"].lower():
            lines = response.text.splitlines()

        parser.parse(lines)

        self.cache[domain] = parser

        return parser

    def allowed(self, url: str) -> bool:
        parser = self.get_parser(url)

        if not parser:
            return True

        return parser.can_fetch("*", url)


robots = RobotsCache()


class URL:
    def __init__(self, address: str, depth: int = 1):
        self.address = address.removesuffix("/")
        self.domain = get_base_domain(address)
        self.depth = depth
        self.status = URLStatus.PENDING


class URLStatus(Enum):
    PENDING = 1
    CRAWLED = 2
    FAILED = 3
    SKIPPED = 4


class Page:
    def __init__(self, url: str, content: str):
        self.id = uuid4()
        self.url = url
        self.content = content
        self.title = None
        self.description = None
        self.noindex = False
        self.links: List[Link] = []

    def parse(self):
        print(f"Parsing page {self.url}")

        soup = BeautifulSoup(self.content, "html.parser")

        self.title = soup.find("title").string
        meta_description = soup.find("meta", property="description")
        self.description = meta_description.get('content') if meta_description else None

        for a in soup.find_all('a'):
            target = urljoin(self.url, a.get("href"))

            source_hostname = urlsplit(self.url).hostname
            target_hostname = urlsplit(target).hostname

            type = LinkType.INTERNAL if source_hostname == target_hostname else LinkType.EXTERNAL

            # Temporary validation to avoid blocks
            if type != LinkType.INTERNAL:
                continue

            rel = a.get("rel") or []
            nofollow = "nofollow" in rel

            link = Link(source=self.url, target=target, type=type, text=a.string, nofollow=nofollow)

            self.links.append(link)

        print(f"Found {len(self.links)} hyperlinks")

        links.extend(self.links)

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


def crawl(address: str, depth: int = 1, max_depth: int = 4):
    url = URL(address=address, depth=depth)

    if is_page_already_crawled(url.address):
        print(f"Skipping {url.address}: already crawled")

        return

    print(f"Checking permissions for {url.domain}")

    if not robots.allowed(url.address):
        print(f"Skipping {url.address}: not allowed")

        return

    # The URL Frontier will handle this case
    # if depth > max_depth:
    #     print(f"Skipping {url.address}: reached max depth")
    #
    #     url.status = URLStatus.SKIPPED

    # TODO: Check if url was skipped before and change depth if lower

    urls.append(url)

    if url.status == URLStatus.SKIPPED:
        return

    print(f"Crawling {url.address}")

    try:
        fetcher = Fetcher(url.address)
        response = fetcher.fetch()

        if response.status_code != 200:
            print(f"Skipping {url.address}: request failed")

            url.status = URLStatus.FAILED

            return

        if not "text/html" in response.headers["Content-Type"].lower():
            print(f"Skipping {url.address}: non html")

            url.status = URLStatus.FAILED

            return

        page = Page(url=url.address, content=response.text)

        page.parse()

        pages.append(page)

        url.status = URLStatus.CRAWLED

        for link in page.links:
            crawl(link.target, depth + 1)

        print(f"Finished crawling {url.address}")
    except Exception as e:
        print(f"Skipping {url.address}: error {e}")

        url.status = URLStatus.FAILED


class Encoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, UUID):
            return str(object)
        if isinstance(object, Enum):
            return object.name
        return super().default(object)


if __name__ == '__main__':
    seed = ["https://quotes.toscrape.com"]

    print(f"Starting crawl with {len(seed)} urls\n")

    for url in seed:
        crawl(url)

    print(f"\nFinished crawl with {len(urls)} urls")

    for index, url in enumerate(urls):
        print(f"[{index}]: {url.address=} {url.status=} {url.depth=}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reports/report_{timestamp}.json"
    urls_data = [u.__dict__ for u in urls]
    links_data = [l.__dict__ for l in links]

    # Temporary report
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({"urls": urls_data, "links": links_data}, f, cls=Encoder, indent=4)
