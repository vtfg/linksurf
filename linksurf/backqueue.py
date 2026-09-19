import asyncio
import time
from asyncio import sleep, Lock, Queue
from datetime import datetime, timezone, timedelta
from typing import cast

from linksurf.common.models import BucketModel, BucketState
from linksurf.common.models import HTTPResponse, URL
from linksurf.common.payload import Payload
from linksurf.logger import Logger
from linksurf.services import Services, Cache, Database
from linksurf.services.cache import ONE_DAY_IN_SECONDS
from linksurf.services.fetcher import ConnectError, ConnectTimeoutError, ReadError, ReadTimeoutError
from linksurf.utils.hashing import bucketize

DEFAULT_DOMAIN_DELAY = 1.0  # seconds
LOCK_DURATION_SECONDS = ONE_DAY_IN_SECONDS
MAX_ACTIVE_DOMAINS = 250  # 5x the Downloader's concurrency to prevent idle workers
MAX_URLS_PER_DOMAIN = 5

LOCK_TRIGGERING_STATUS_CODES = {403, 429, 500, 502, 503}
LOCK_TRIGGERING_EXCEPTIONS = (ConnectTimeoutError, ReadTimeoutError, ReadError, ConnectError)


class BackQueue:
    database: Database
    cache: Cache

    def __init__(self):
        self.buckets: list[int] = []
        self._draining_buckets: set[int] = set()
        self._in_flight_buckets: dict[int, int] = {}
        self._assignment_revisions: dict[int, int] = {}

        # general lock for insert/remove operations in internal dicts
        self.lock = Lock()

        # domain: Queue[Payload]
        self.queues: dict[str, Queue[Payload]] = {}

        # TODO: this should be an automatically sorted data structure for performance reasons (Min-Heap?)
        # domain: release time
        self.release_times: dict[str, float] = {}

        # domain: Lock
        self.locks: dict[str, Lock] = {}

        self.ready = False
        self._draining = False

    async def on_start(self, services: Services):
        self.ready = False

        self.database = services.database
        self.cache = services.cache

        Logger().info("back_queue.start", message=f"Enqueueing up to {MAX_ACTIVE_DOMAINS} domains on demand.")

        self.ready = True

    async def on_stop(self):
        Logger().info("back_queue.stop")

        self.ready = False

    def set_buckets(self, buckets: list[int] | list[BucketModel]) -> None:
        """
        Set bucket admission from IDs during startup or persisted assignments
        during worker synchronization.
        """

        if not buckets:
            self.buckets = []
            self._draining_buckets.clear()
            self._assignment_revisions.clear()

            return

        if isinstance(buckets[0], int):
            bucket_ids = cast(list[int], buckets)
            self.buckets = sorted(set(bucket_ids))
            self._draining_buckets.clear()
            self._assignment_revisions.clear()

            return

        assignments = cast(list[BucketModel], buckets)

        self.buckets = sorted(
            assignment.id
            for assignment in assignments
            if assignment.state in {BucketState.IDLE, BucketState.ACTIVE}
        )
        self._draining_buckets = {
            assignment.id for assignment in assignments if assignment.state == BucketState.DRAINING
        }
        self._assignment_revisions = {assignment.id: assignment.revision for assignment in assignments}

        Logger().info(
            "back_queue.assignment",
            buckets=self.buckets,
            draining_buckets=sorted(self._draining_buckets),
        )

    async def bucket_states(self) -> dict[int, BucketState]:
        """
        Return local activity for buckets that this worker may still fetch.
        """

        async with self.lock:
            states: dict[int, BucketState] = {}

            for bucket in self.buckets:
                states[bucket] = BucketState.ACTIVE if self._bucket_has_work(bucket) else BucketState.IDLE

            return states

    async def drained_buckets(self) -> list[int]:
        """
        Return draining buckets whose local queue and in-flight work are empty.
        """

        async with self.lock:
            return sorted(bucket for bucket in self._draining_buckets if not self._bucket_has_work(bucket))

    async def wait_for_drain(self, timeout_seconds: float) -> bool:
        """
        Wait for all locally admitted work to finish after global admission has stopped.
        """

        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            async with self.lock:
                if not self._has_local_work():
                    return True

            await sleep(0.25)

        return False

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
            # outside the lock below because _enqueue_new_domain already takes
            while len(self.queues) < MAX_ACTIVE_DOMAINS:
                if not await self._enqueue_new_domain():
                    break

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
                        bucket = bucketize(domain)
                        self._in_flight_buckets[bucket] = self._in_flight_buckets.get(bucket, 0) + 1

                        return payload, lock

                # temporary log used to check how many and how much time the workers stay idle
                # if higher than expected the MAX_ACTIVE_DOMAINS could be increased or new seeds from different domains added
                # Logger().debug("back_queue.debug", message="No available domains.")

            await sleep(1)

    async def report(self, payload: Payload, response: HTTPResponse | None, exception: Exception | None = None) -> None:
        """
        Adjusts a domain's delay based on the response's status code and elapsed time.

        A blocking status code or a connection exception causes a temporary domain lock and eventually a permanent block.
        """

        domain = payload.url.domain

        try:
            delay_seconds = DEFAULT_DOMAIN_DELAY

            should_lock = (
                    (response is not None and response.status_code in LOCK_TRIGGERING_STATUS_CODES)
                    or isinstance(exception, LOCK_TRIGGERING_EXCEPTIONS)
            )

            if should_lock:
                until = datetime.now(timezone.utc) + timedelta(seconds=LOCK_DURATION_SECONDS)
                reason = f"Received status {response.status_code}" if response is not None else f"Caught exception {type(exception).__name__}"

                try:
                    status = await self.database.lock_domain(domain, until, reason)

                    Logger().warning("back_queue.locked", domain=domain, status=status.value, reason=reason)
                except Exception as e:
                    Logger().error("back_queue.error", message="Failed to lock domain.", exception=str(e))
            elif response is not None:
                # since robots.txt's Crawl-Delay is no longer used this formula helps to apply a slightly increased delay
                delay_seconds = response.elapsed_ms / 1000 + DEFAULT_DOMAIN_DELAY

                try:
                    await self.database.unlock_domain(domain)
                except Exception as e:
                    Logger().error("back_queue.error", message="Failed to reset domain lock.", exception=str(e))

            self.release_times[domain] = time.time() + delay_seconds

            Logger().debug("back_queue.debug", message=f"Adjusted {domain} delay to {delay_seconds}s")

            if should_lock or self.queues[domain].empty():
                asyncio.create_task(self._cleanup_domain(domain))
        finally:
            await self.complete(payload)

    async def complete(self, payload: Payload) -> None:
        """
        Mark a payload selected by ``next`` as no longer in flight.
        """

        bucket = bucketize(payload.url.domain)

        async with self.lock:
            count = self._in_flight_buckets.get(bucket, 0)

            if count <= 1:
                self._in_flight_buckets.pop(bucket, None)
            else:
                self._in_flight_buckets[bucket] = count - 1

    def drain(self) -> None:
        """
        Signal to stop enqueueing new domains.
        """

        self._draining = True

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

        if self._draining:
            return False

        async with self.lock:
            if len(self.queues) >= MAX_ACTIVE_DOMAINS:
                return False

            current_domains = list(self.queues.keys())

            try:
                excluded_domains = await self.database.get_excluded_domains()
            except Exception as e:
                Logger().error("back_queue.error", message="Failed to get excluded domains.", exception=str(e))

                excluded_domains = []

            fetchable_buckets = [bucket for bucket in self.buckets if bucket not in self._draining_buckets]

            if not fetchable_buckets:
                return False

            new_domains = await self.database.get_distinct_domains(current_domains + excluded_domains,
                                                                   fetchable_buckets,
                                                                   limit=1)

            # Logger().debug("back_queue.debug", new=new_domains, excluded=excluded_domains, current=current_domains)

            if not new_domains:
                return False

            domain = new_domains[0]

            urls = await self.database.get_domain_urls(domain, limit=MAX_URLS_PER_DOMAIN)

            if not urls:
                return False

            for url in urls:
                # fresh Payload because these URLs have never been crawled
                payload = Payload(
                    url=URL(url.address),
                    priority=url.priority,
                    correlation_id=url.correlation_id,
                    discovered_at=url.discovered_at,
                )

                await self.put(payload)

            Logger().debug("back_queue.debug", message=f"Enqueueing {domain} with {len(urls)} URLs.")

            return True

    def _bucket_has_work(self, bucket: int) -> bool:
        if self._in_flight_buckets.get(bucket, 0) > 0:
            return True

        return any(bucketize(domain) == bucket and queue.qsize() > 0 for domain, queue in self.queues.items())

    def _has_local_work(self) -> bool:
        return bool(self._in_flight_buckets) or any(queue.qsize() > 0 for queue in self.queues.values())
