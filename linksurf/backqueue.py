import asyncio
import time
from asyncio import sleep, Lock, Queue

from linksurf.common.models import HTTPResponse, URL
from linksurf.common.payload import Payload
from linksurf.logger import Logger
from linksurf.services import Services, Cache, Database
from linksurf.services.cache import ONE_DAY_IN_SECONDS

DEFAULT_DOMAIN_DELAY = 1.0  # seconds
MAX_ACTIVE_DOMAINS = 100  # 5x the Downloader's concurrency to prevent idle workers
MAX_URLS_PER_DOMAIN = 5


class BackQueue:
    database: Database
    cache: Cache

    def __init__(self):
        # general lock for insert/remove operations in internal dicts
        self.lock = Lock()

        # domain: Queue[Payload]
        self.queues: dict[str, Queue[Payload]] = {}

        # TODO: this should be an automatically sorted data structure for performance reasons (Min-Heap?)
        # domain: release time
        self.release_times: dict[str, float] = {}

        # domain: Lock
        self.locks: dict[str, Lock] = {}

    async def on_start(self, services: Services):
        """
        Gathers domains, URLs and release times from disk (Database).
        """

        self.database = services.database
        self.cache = services.cache

        Logger().info("back_queue.start", message=f"Querying and enqueueing {MAX_ACTIVE_DOMAINS} domains.")

        while len(self.queues) < MAX_ACTIVE_DOMAINS:
            if not await self._enqueue_new_domain():
                Logger().warning("back_queue.warning", message="No more pending domains available.")

                break

    async def on_stop(self):
        """
        Writes in-memory data (pending URLs and domains' release time) to Database.
        """

        # TODO: ^

        Logger().info("back_queue.stop")

    async def put(self, payload: Payload) -> None:
        """
        Puts a new payload into it's domain's back queue.

        Must be called while holding `self.lock`.
        """

        domain = payload.url.domain
        port = payload.url.port

        if domain not in self.queues:
            self.queues[domain] = Queue()

        await self.queues[domain].put(payload)

        if domain not in self.locks:
            self.locks[domain] = Lock()

        if domain not in self.release_times:
            release_time: float | None = None

            try:
                release_time = await self.cache.get_domain_release_time(domain, port)

                if release_time is not None:
                    Logger().debug("back_queue.debug", message=f"Read release time cache for {domain}",
                                   data=release_time)
            except Exception as e:
                Logger().error("back_queue.error", message="Failed to get domain release time.",
                               exception=str(e))

            self.release_times[domain] = release_time or time.time()

    async def next(self) -> tuple[Payload, Lock]:
        """
        Retrieves the next available URL from a ready-to-be-crawled unlocked domain.

        If no domain is ready, sleeps for 1s and re-checks all domains.
        """

        while True:
            # scanning and consuming must be atomic to prevent TOCTOU window errors
            # ^ mostly KeyError from trying to read from release_time a few milliseconds after the domain has been cleaned up
            async with self.lock:
                for domain, queue in self.queues.items():
                    now = time.time()

                    size = queue.qsize()
                    release_time = self.release_times[domain]
                    lock = self.locks[domain]

                    if size >= 1 and now >= release_time and not lock.locked():
                        # increase immediately in case the caller task fails unexpectedly and doesn't send a report
                        self.release_times[domain] = now + DEFAULT_DOMAIN_DELAY

                        payload = await queue.get()

                        return payload, lock

                Logger().debug("back_queue.debug", message="No available domains.")

            await sleep(1)

    async def report(self, payload: Payload, response: HTTPResponse | None):
        """
        Receives an URL and adjusts the domain's delay based on the response's status code and elapsed time.
        """

        # TODO: define how to exponentially back-off or dynamically block a domain
        # ^ the system needs to keep track of previous responses

        domain = payload.url.domain
        port = payload.url.port

        delay_seconds = DEFAULT_DOMAIN_DELAY
        penalized = False

        if response is not None:
            match response.status_code:
                case 429 | 500:
                    delay_seconds = ONE_DAY_IN_SECONDS
                    penalized = True

                    try:
                        await self.cache.save_domain_release_time(domain, port, time.time() + delay_seconds)
                    except Exception as e:
                        Logger().error("back_queue.error", message="Failed to save domain release time.",
                                       exception=str(e))
                case _:
                    # since robots.txt's Crawl-Delay is no longer used this formula helps to apply a slightly increased delay
                    delay_seconds = response.elapsed_ms / 1000 + DEFAULT_DOMAIN_DELAY

        self.release_times[domain] = time.time() + delay_seconds

        Logger().debug("back_queue.debug", message=f"Adjusted {domain} delay to {delay_seconds}s")

        if penalized or self.queues[domain].empty():
            asyncio.create_task(self._cleanup_domain(domain))

    async def _cleanup_domain(self, domain: str) -> None:
        """
        Deletes all domain related elements (queue, release time and lock) from in-memory properties and replaces with a new one.
        """

        lock = self.locks.get(domain)

        if lock is None:
            return

        async with lock:
            async with self.lock:
                self.queues.pop(domain, None)
                self.release_times.pop(domain, None)
                self.locks.pop(domain, None)

        Logger().debug("back_queue.debug", message=f"Removed domain {domain}.")

        await self._enqueue_new_domain()

    async def _enqueue_new_domain(self) -> bool:
        """
        Returns `True` if a new domain was successfully enqueued.
        """

        async with self.lock:
            if len(self.queues) >= MAX_ACTIVE_DOMAINS:
                return False

            current_domains = list(self.queues.keys())

            new_domains = await self.database.get_distinct_domains(current_domains, limit=1)

            if not new_domains:
                return False

            domain = new_domains[0]

            urls = await self.database.get_domain_urls(domain, limit=MAX_URLS_PER_DOMAIN)

            if not urls:
                return False

            for url in urls:
                payload = Payload(
                    url=URL(url.address),
                    priority=url.priority,
                    correlation_id=url.correlation_id,
                    status=url.status,
                    content=url.content,
                    redirects=url.redirects,
                    request=url.request,
                    response=url.response,
                    metadata=url.metadata,
                    discovered_at=url.discovered_at,
                    fetched_at=url.fetched_at,
                )

                await self.put(payload)

            Logger().debug("back_queue.debug", message=f"Enqueueing {domain} with {len(urls)} URLs.")

            return True
