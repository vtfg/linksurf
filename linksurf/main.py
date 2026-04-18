import asyncio
import hashlib

from linksurf.cache import init_redis, get_redis
from linksurf.database import Page, init_database, save_links, save_page, URL, LinkType
from linksurf.fetcher import Fetcher
from linksurf.frontier import URLFrontier
from linksurf.helpers import get_domain_name
from linksurf.parser import HTMLParser
from linksurf.robots import Robots
from linksurf.storage import init_storage, upload_html

robots = Robots()


async def crawl(url: URL, frontier: URLFrontier):
    domain_name = get_domain_name(url.address)

    await frontier.wait_for_domain(domain_name)

    url_hash = hashlib.sha256(url.address.encode()).hexdigest()

    print(f"Checking permissions for {url.address}")

    if not await robots.can_fetch(url.address):
        print(f"Skipping {url.address}: not allowed")
        return

    print(f"Crawling {url.address}")

    try:
        fetcher = Fetcher()

        response = fetcher.fetch(url.address)

        await frontier.mark_domain_crawled(domain_name)

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
                await frontier.push(URL(address=link.target, depth=url.depth + 1))

        print(f"Finished crawling {url.address}")
    except Exception as e:
        print(f"Skipping {url.addressx}: error {e}")


async def main():
    await init_database()
    await init_redis()
    init_storage()

    frontier = URLFrontier(get_redis())

    pages_before = await Page.count()

    seed = ["https://quotes.toscrape.com"]

    print(f"Starting crawl with {len(seed)} seed urls\n")

    for address in seed:
        added = await frontier.push(URL(address=address))

        if not added:
            print(f"Skipping {address}: already crawled")

    while not await frontier.empty():
        url = await frontier.pop()

        await crawl(url, frontier)

    pages_after = await Page.count()

    print(f"\nPages before: {pages_before} | Pages after: {pages_after} | New: {pages_after - pages_before}")


if __name__ == '__main__':
    asyncio.run(main())
