import asyncio
import hashlib
from queue import Queue

from linksurf.cache import init_redis
from linksurf.database import Page, init_database, save_links, save_page, URL, LinkType
from linksurf.fetcher import Fetcher
from linksurf.parser import HTMLParser
from linksurf.robots import Robots
from linksurf.storage import init_storage, upload_html

robots = Robots()
queue: Queue[URL] = Queue()


async def is_page_already_crawled(url_hash: str) -> bool:
    return await Page.find_one(Page.url_hash == url_hash) is not None


async def crawl(url: URL):
    url_hash = hashlib.sha256(url.address.encode()).hexdigest()

    if await is_page_already_crawled(url_hash):
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

        print(f"Parsing page {url.address}")

        metadata, links = HTMLParser.parse(url.address, response.text)

        print(f"Found {len(links)} hyperlinks")

        html_url = upload_html(url_hash, response.text)

        await save_page(url.address, url_hash, html_url, metadata)
        await save_links(links)

        for link in links:
            # Temporary validation to avoid blocks
            if link.type == LinkType.INTERNAL:
                queue.put(URL(address=link.target, depth=url.depth + 1))

        print(f"Finished crawling {url.address}")
    except Exception as e:
        print(f"Skipping {url.address}: error {e}")


async def main():
    await init_database()
    await init_redis()
    init_storage()

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
