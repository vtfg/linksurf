import asyncio
from queue import Queue
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from linksurf.database import Link, LinkType, Metadata, MetaTag, Page, init, save_links, save_page
from linksurf.helpers import get_env, get_base_domain

load_dotenv()

proxy_http = get_env("PROXY_HTTP_URL")
proxy_https = get_env("PROXY_HTTPS_URL")
user_agent = get_env("USER_AGENT")


class Fetcher:
    def fetch(self, url: str) -> requests.Response:
        split = urlsplit(url)

        if split.scheme in ["http", "https"]:
            return self._http(url)
        else:
            raise NotImplementedError()

    def _http(self, url: str) -> requests.Response:
        headers = {
            "User-Agent": user_agent,
        }

        proxies = {
            "http": proxy_http,
            "https": proxy_https,
        }

        return requests.get(url, headers=headers, proxies=proxies)


class RobotsCache:
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.cache: dict[str, RobotFileParser] = {}

    def _get_parser(self, url: str) -> RobotFileParser | None:
        domain = get_base_domain(url)

        if domain in self.cache:
            print(f"Using cached robots for {domain}")

            return self.cache[domain]

        print(f"Fetching robots for {domain}")

        robots_url = f"{domain}/robots.txt"

        fetcher = Fetcher()
        response = fetcher.fetch(robots_url)

        parser = RobotFileParser()

        lines = []

        if response.status_code == 200 and "text/plain" in response.headers["Content-Type"].lower():
            lines = response.text.splitlines()

        parser.parse(lines)

        self.cache[domain] = parser

        return parser

    def allowed(self, url: str) -> bool:
        parser = self._get_parser(url)

        if not parser:
            return True

        return parser.can_fetch("*", url)


robots = RobotsCache()


class URL:
    def __init__(self, address: str, depth: int = 0):
        self.address = address.removesuffix("/")
        self.domain = get_base_domain(address)
        self.depth = depth


class Parser:
    def parse(self, url: str, html: str) -> tuple[Metadata, list[Link]]:
        print(f"Parsing page {url}")

        soup = BeautifulSoup(html, "html.parser")

        html_tag = soup.find("html")
        lang = html_tag.get("lang") if html_tag else None

        title_tag = soup.find("title")
        title = title_tag.string if title_tag else None

        meta_tags = []
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                meta_tags.append(MetaTag(name=name, content=content))

        description = next((m.content for m in meta_tags if m.name == "description"), None)

        metadata = Metadata(title=title, description=description, lang=lang, tags=meta_tags)

        parsed_links = []
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue

            target = urljoin(url, href)

            source_hostname = urlsplit(url).hostname
            target_hostname = urlsplit(target).hostname

            link_type = LinkType.INTERNAL if source_hostname == target_hostname else LinkType.EXTERNAL

            # Temporary validation to avoid blocks
            if link_type != LinkType.INTERNAL:
                continue

            rel = a.get("rel") or []
            nofollow = "nofollow" in rel

            parsed_links.append(Link(source=url, target=target, type=link_type, text=a.string, nofollow=nofollow))

        print(f"Found {len(parsed_links)} hyperlinks")

        return metadata, parsed_links


queue: Queue[URL] = Queue()


async def is_page_already_crawled(address: str) -> bool:
    return await Page.find_one(Page.url == address) is not None


async def crawl(url: URL):
    if await is_page_already_crawled(url.address):
        print(f"Skipping {url.address}: already crawled")

        return

    print(f"Checking permissions for {url.domain}")

    if not robots.allowed(url.address):
        print(f"Skipping {url.address}: not allowed")

        return

    print(f"Crawling {url.address}")

    try:
        fetcher = Fetcher()

        response = fetcher.fetch(url.address)

        if response.status_code != 200:
            print(f"Skipping {url.address}: request failed")

            return

        if "text/html" not in response.headers["Content-Type"].lower():
            print(f"Skipping {url.address}: non html")

            return

        parser = Parser()
        metadata, parsed_links = parser.parse(url.address, response.text)

        await save_page(url.address, response.text, metadata)
        await save_links(parsed_links)

        for link in parsed_links:
            queue.put(URL(address=link.target, depth=url.depth + 1))

        print(f"Finished crawling {url.address}")
    except Exception as e:
        print(f"Skipping {url.address}: error {e}")


async def main():
    await init()

    pages_before = await Page.count()

    seed = ["https://quotes.toscrape.com"]

    print(f"Starting crawl with {len(seed)} seed urls\n")

    for address in seed:
        queue.put(URL(address=address))

    while not queue.empty():
        url = queue.get()

        await crawl(url)

    pages_after = await Page.count()

    print(f"\nPages before: {pages_before} | Pages after: {pages_after} | New: {pages_after - pages_before}")


if __name__ == '__main__':
    asyncio.run(main())
