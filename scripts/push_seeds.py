#!/usr/bin/env python

import asyncio
import sys
from urllib.parse import urlparse

from linksurf.cache import init_redis, get_redis
from linksurf.database import Page, init_database, URL
from linksurf.frontier import URLFrontier
from linksurf.storage import init_storage


async def main(urls: list[str]):
    await init_database()
    await init_redis()
    await init_storage()

    frontier = URLFrontier(get_redis())

    print(f"Pushing {len(urls)} url(s)\n")

    for address in urls:
        added = await frontier.push(URL(address=address))

        status = "queued" if added else "skipped (already seen)"

        print(f"  {address} — {status}")

    pages = await Page.count()

    print(f"\nDone. Pages in database: {pages}")


def validate_urls(urls: list[str]) -> None:
    invalid = [u for u in urls if not urlparse(u).scheme in ("http", "https") or not urlparse(u).netloc]

    if invalid:
        for u in invalid:
            print(f"Invalid URL: {u}", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Usage: push_seeds.py <url> [url ...]", file=sys.stderr)

        sys.exit(1)

    validate_urls(args)

    asyncio.run(main(args))
