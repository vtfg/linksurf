from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from linksurf.backqueue import BackQueue
from linksurf.common.constants import BUCKET_COUNT, MAX_BUCKET_MOVES
from linksurf.common.models import BucketState, WorkerModel, WorkerStatus
from linksurf.logger import Logger
from linksurf.services import Database, Lock
from linksurf.services import Services

BUCKET_COORDINATION_LOCK = "buckets"
WORKER_LEASE_SECONDS = 120


class Worker:
    """
    This process's membership lease and virtual-bucket ownership protocol.

    The application decides whether the process is ready to participate. The
    worker persists that decision, reconciles bucket ownership, and keeps the
    BackQueue's local admission policy in sync with Database.
    """

    database: Database
    lock: Lock

    def __init__(
            self,
            services: Services,
            back_queue: BackQueue,
            *,
            metadata: dict[str, Any],
    ) -> None:
        self.identifier = uuid4().hex
        self.metadata = metadata

        self.services = services
        self.back_queue = back_queue

        self.started_at = datetime.now(timezone.utc)
        self.status = WorkerStatus.READY
        self.buckets: list[int] = []

        self.database = services.database
        self.lock = services.lock

    async def on_start(self) -> None:
        """
        Initialize bucket records and establish this worker's membership.
        """

        await self.database.ensure_bucket_records(BUCKET_COUNT)

        await self.refresh()

        Logger().info("worker.start", identifier=self.identifier)

    async def on_stop(self) -> None:
        """
        Cede ownership after the application has drained local work.
        """

        await self.release()

        Logger().info("worker.stop", identifier=self.identifier)

    async def refresh(self) -> None:
        """
        Refresh the membership lease, publish local work, then reconcile.
        """

        await self.upsert()

        await self.coordinate()

        Logger().info("worker.membership_refreshed", identifier=self.identifier, status=self.status.value)

    async def coordinate(self) -> None:
        """
        Publish local bucket activity and reconcile bucket ownership.
        """

        if self.back_queue.ready:
            await self.publish_local_bucket_states()

        await self.acquire()

    async def upsert(self) -> None:
        now = datetime.now(timezone.utc)

        await self.database.upsert_worker(WorkerModel(
            id=self.identifier,
            status=self.status,
            started_at=self.started_at,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=WORKER_LEASE_SECONDS),
            metadata=self.metadata,
        ))

        Logger().info("worker.registered", identifier=self.identifier, status=self.status.value)

    def mark_draining(self) -> None:
        """
        Stop local admission immediately without performing I/O.
        """

        self.status = WorkerStatus.DRAINING

        self.back_queue.drain()

    async def acquire(self) -> None:
        """
        Serialize allocation decisions and update local queue assignments.
        """

        async with self.lock.acquire(BUCKET_COORDINATION_LOCK, blocking_timeout_seconds=120):
            # Learn about a handoff before reconciling so the current owner can
            # stop admission and attest that the bucket has actually drained.
            await self.sync_backqueue_assignments()

            await self.reconcile()

        await self.sync_backqueue_assignments()

    async def release(self) -> None:
        """
        Release all owned buckets after the BackQueue has drained.
        """

        async with self.lock.acquire(BUCKET_COORDINATION_LOCK):
            buckets = await self.database.get_owned_buckets(self.identifier)

            for bucket in buckets:
                await self.database.set_bucket_assignment(
                    bucket.id, None, BucketState.UNASSIGNED,
                )

            await self.database.delete_worker(self.identifier)

            Logger().info("worker.released", identifier=self.identifier, buckets=[bucket.id for bucket in buckets])

    async def publish_local_bucket_states(self) -> None:
        await self.database.sync_owned_bucket_states(
            self.identifier,
            await self.back_queue.bucket_states(),
        )

    async def sync_backqueue_assignments(self) -> None:
        assignments = await self.database.get_owned_buckets(self.identifier)

        self.buckets = [
            bucket.id for bucket in assignments
            if bucket.state in {BucketState.IDLE, BucketState.ACTIVE}
        ]

        self.back_queue.set_buckets(assignments)

    async def reconcile(self) -> None:
        """
        Apply deterministic, bucket-count balancing for all live workers.
        """

        database = self.database
        now = datetime.now(timezone.utc)

        expired_workers = await database.delete_expired_workers(now)

        if expired_workers:
            Logger().warning("worker.expired_removed", count=expired_workers)

        live_workers = await database.get_live_workers(now)
        live_ids = {worker.id for worker in live_workers}
        ready_ids = sorted(worker.id for worker in live_workers if worker.status == WorkerStatus.READY)
        buckets = await database.get_buckets()

        # A lost owner cannot finish its local queue. Reclaim it; an already-reserved,
        # live successor may continue from MongoDB's durable pending URL records.
        for bucket in buckets:
            if bucket.owner_id is None or bucket.owner_id in live_ids:
                continue

            if bucket.state == BucketState.DRAINING and bucket.successor_id in ready_ids:
                successor = bucket.successor_id
                await database.set_bucket_assignment(bucket.id, successor, BucketState.IDLE)
                Logger().warning("worker.bucket_promoted", bucket=bucket.id,
                                 owner=successor, reason="expired_owner")
            else:
                await database.set_bucket_assignment(bucket.id, None, BucketState.UNASSIGNED)
                Logger().warning("worker.bucket_released", bucket=bucket.id, reason="expired_owner")

        if not ready_ids:
            return

        buckets = await database.get_buckets()
        targets = self.target_counts(ready_ids, len(buckets))
        effective_owner = {
            bucket.id: (
                bucket.successor_id
                if bucket.state == BucketState.DRAINING and bucket.successor_id in ready_ids
                else bucket.owner_id
            )
            for bucket in buckets
        }
        loads = {worker_id: 0 for worker_id in ready_ids}

        for owner in effective_owner.values():
            if owner in loads:
                loads[owner] += 1

        def receiver() -> str | None:
            candidates = [worker_id for worker_id in ready_ids if loads[worker_id] < targets[worker_id]]
            return min(candidates, key=lambda worker_id: (loads[worker_id], worker_id), default=None)

        # Free buckets are always assigned before any worker is asked to give work away.
        for bucket in buckets:
            if bucket.state != BucketState.UNASSIGNED:
                continue

            destination = receiver()
            if destination is None:
                break

            await database.set_bucket_assignment(bucket.id, destination, BucketState.IDLE)
            loads[destination] += 1
            effective_owner[bucket.id] = destination
            Logger().info("worker.bucket_assigned", bucket=bucket.id, owner=destination, reason="unassigned")

        buckets = await database.get_buckets()
        max_moves = len(buckets) if MAX_BUCKET_MOVES == "all" else int(MAX_BUCKET_MOVES)
        moves = 0
        for state in (BucketState.IDLE, BucketState.ACTIVE):
            for bucket in buckets:
                if moves >= max_moves:
                    break

                source = effective_owner[bucket.id]
                source_target = targets.get(source, 0)

                if bucket.state != state or source is None or loads.get(source, 0) <= source_target:
                    continue

                destination = receiver()
                if destination is None:
                    break

                # Persisted IDLE can lag the owner's in-memory queue and
                # in-flight counters. Every handoff must therefore drain under
                # the old owner before the successor is allowed to admit work.
                if await database.mark_bucket_draining(bucket.id, source, destination):
                    Logger().info("worker.bucket_draining", bucket=bucket.id,
                                  source=source, successor=destination, previous_state=state.value)
                else:
                    continue

                loads[source] -= 1
                loads[destination] += 1
                effective_owner[bucket.id] = destination
                moves += 1

            if moves >= max_moves:
                break

        # Only this process can attest that its local draining queue is empty.
        if self.back_queue.ready:
            for bucket_id in await self.back_queue.drained_buckets():
                bucket = next((item for item in buckets if item.id == bucket_id), None)

                if bucket is None or bucket.successor_id is None:
                    continue

                successor_id = bucket.successor_id

                if await database.promote_drained_bucket(bucket.id, self.identifier, successor_id):
                    Logger().info("worker.bucket_promoted", bucket=bucket.id,
                                  owner=successor_id, reason="drained")

    @staticmethod
    def target_counts(worker_ids: list[str], bucket_count: int) -> dict[str, int]:
        base, remainder = divmod(bucket_count, len(worker_ids))

        return {
            worker_id: base + (1 if index < remainder else 0)
            for index, worker_id in enumerate(worker_ids)
        }
