import asyncio
from queue import Queue
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup

from linksurf.cache import init_redis
from linksurf.database import Link, LinkType, Metadata, MetaTag, Page, init_database, save_links, save_page
from linksurf.fetcher import Fetcher
from linksurf.helpers import get_base_domain
from linksurf.robots import Robots

robots = Robots()


class URL:
    def __init__(self, address: str, depth: int = 0):
        self.address = address
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

        links = []
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

            links.append(Link(source=url, target=target, type=link_type, text=a.string, nofollow=nofollow))

        print(f"Found {len(links)} hyperlinks")

        return metadata, links


queue: Queue[URL] = Queue()


async def is_page_already_crawled(address: str) -> bool:
    return await Page.find_one(Page.url == address) is not None


async def crawl(url: URL):
    if await is_page_already_crawled(url.address):
        print(f"Skipping {url.address}: already crawled")

        return

    print(f"Checking permissions for {url.address}")

    if not await robots.can_fetch(url.address):
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
    await init_database()

    await init_redis()

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
