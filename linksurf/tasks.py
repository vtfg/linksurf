import asyncio
import hashlib

from celery import Celery
from celery.signals import worker_process_init
from celery.utils.log import get_task_logger

from linksurf.cache import get_redis
from linksurf.database import URL
from linksurf.database import save_links, save_page, LinkType
from linksurf.fetcher import Fetcher
from linksurf.frontier import URLFrontier
from linksurf.helpers import get_domain_name
from linksurf.helpers import get_env
from linksurf.parser import HTMLParser
from linksurf.robots import Robots
from linksurf.storage import upload_html

logger = get_task_logger(__name__)

celery = Celery(
    "linksurf",
    broker=get_env("RABBITMQ_URL", default="amqp://guest:guest@localhost/"),
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def init_worker(**kwargs):
    global _loop

    from linksurf.cache import init_redis
    from linksurf.database import init_database
    from linksurf.storage import init_storage

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    _loop.run_until_complete(init_database())
    _loop.run_until_complete(init_redis())
    _loop.run_until_complete(init_storage())


@celery.task(name="linksurf.crawl")
def crawl_task(address: str, depth: int) -> None:
    url = URL(address=address, depth=depth)
    frontier = URLFrontier(get_redis())

    _loop.run_until_complete(crawl(url, frontier))


robots = Robots()


async def crawl(url: URL, frontier: URLFrontier) -> None:
    domain_name = get_domain_name(url.address)

    url_hash = hashlib.sha256(url.address.encode()).hexdigest()

    print(f"Checking permissions for {url.address}")

    if not await robots.can_fetch(url.address):
        print(f"Skipping {url.address}: not allowed")
        return

    await frontier.acquire_domain_slot(domain_name)

    print(f"Crawling {url.address}")

    try:
        fetcher = Fetcher()
        response = await asyncio.to_thread(fetcher.fetch, url.address)

        if response.status_code != 200:
            print(f"Skipping {url.address}: request failed")
            return

        if "text/html" not in response.headers["Content-Type"].lower():
            print(f"Skipping {url.address}: non html")
            return

        print(f"Parsing page {url.address}")

        metadata, links = HTMLParser.parse(url.address, response.text)

        print(f"Found {len(links)} hyperlinks")

        html_url = await upload_html(url_hash, response.text)

        await save_page(url.address, url_hash, html_url, metadata)
        await save_links(links)

        for link in links:
            if link.type == LinkType.INTERNAL:
                await frontier.push(URL(address=link.target, depth=url.depth + 1))

        print(f"Finished crawling {url.address}")
    except Exception as e:
        print(f"Skipping {url.address}: error {e}")
