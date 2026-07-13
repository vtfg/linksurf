import time
from asyncio import sleep, Lock, Queue

from linksurf.common.models import HTTPResponse
from linksurf.common.payload import Payload
from linksurf.logger import Logger
from linksurf.services import Services
from linksurf.services.cache import ONE_DAY_IN_SECONDS

DEFAULT_DOMAIN_DELAY = 1.0  # seconds


class BackQueue:
    def __init__(self):
        # domain: Queue[Payload]
        self.queues: dict[str, Queue[Payload]] = {}

        # TODO: this should be an automatically sorted data structure for performance reasons (Min-Heap?)
        # domain: release time
        self.release_times: dict[str, float] = {}

        # domain: Lock
        self.locks: dict[str, Lock] = {}

    async def on_start(self, services: Services):
        """
        Gathers URLs and domains' release times from disks (Database).
        """

        # TODO: ^

        pass

    async def on_stop(self):
        """
        Writes in-memory data (pending URLs and domains' release time) to Database.
        """

        # TODO: ^

        pass

    async def put(self, payload: Payload) -> None:
        """
        Puts a new payload into it's domain's back queue.
        """

        domain = payload.url.domain

        if domain not in self.queues:
            self.queues[domain] = Queue()

        await self.queues[domain].put(payload)

        if domain not in self.locks:
            self.locks[domain] = Lock()

        if domain not in self.release_times:
            self.release_times[domain] = time.time()

    async def next(self) -> tuple[Payload, Lock]:
        """
        Retrieves the next available URL from a ready-to-be-crawled domain.

        Awaits for the domain lock before returning it.

        If no domain is ready, sleeps for 1s and re-checks all domains.
        """

        while True:
            for domain, queue in self.queues.items():
                now = time.time()

                size = queue.qsize()
                release_time = self.release_times[domain]
                lock = self.locks[domain]

                if size >= 1 and now >= release_time and not lock.locked():
                    # increase immediately in case the caller task fails unexpectedly and doesn't send a report
                    self.release_times[domain] = now + DEFAULT_DOMAIN_DELAY

                    return await queue.get(), self.locks[domain]

            await sleep(1)

    async def report(self, payload: Payload, response: HTTPResponse | None):
        """
        Receives an URL and adjusts the domain's delay based on the response's status code and elapsed time.
        """

        # TODO: define how to exponentially back-off or dynamically block a domain
        # ^ the system needs to keep track of previous responses

        domain = payload.url.domain

        delay_seconds = DEFAULT_DOMAIN_DELAY

        if response is not None:
            match response.status_code:
                case 429 | 500:
                    delay_seconds = ONE_DAY_IN_SECONDS
                case _:
                    # since robots.txt's Crawl-Delay is no longer used this formula helps to apply a slightly increased delay
                    delay_seconds = response.elapsed_ms / 1000 + DEFAULT_DOMAIN_DELAY

        Logger().debug("back_queue.debug", message=f"Adjusted {domain} delay to {delay_seconds}s")

        self.release_times[domain] = time.time() + delay_seconds
