from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator

import redis.asyncio as redis
from redis.asyncio.lock import Lock as RedisClientLock
from redis.exceptions import LockError as RedisClientLockError

from linksurf.common.settings import Settings
from linksurf.services.base import Service

DEFAULT_LOCK_TTL_SECONDS = 30
DEFAULT_BLOCKING_TIMEOUT_SECONDS = 10

_LOCK_KEY_PREFIX = "linksurf:lock:"


class LockError(Exception):
    pass


class LockAcquisitionError(LockError):
    pass


class LockOwnershipError(LockError):
    pass


class LockLease:
    def __init__(self, key: str, service: "Lock"):
        self.key = key
        self._service = service

    async def owned(self) -> bool:
        return await self._service.owned(self)

    async def extend(self, additional_seconds: float) -> None:
        await self._service.extend(self, additional_seconds)


class Lock(Service):
    NAME = "lock"

    def acquire(
            self,
            name: str,
            *,
            ttl_seconds: float = DEFAULT_LOCK_TTL_SECONDS,
            blocking_timeout_seconds: float = DEFAULT_BLOCKING_TIMEOUT_SECONDS,
    ) -> AsyncContextManager[LockLease]:
        raise NotImplementedError()

    async def locked(self, name: str) -> bool:
        raise NotImplementedError()

    async def owned(self, lease: LockLease) -> bool:
        raise NotImplementedError()

    async def extend(self, lease: LockLease, additional_seconds: float) -> None:
        raise NotImplementedError()


class RedisLock(Lock):
    def __init__(self, host: str, port: int, username: str = "default", password: str | None = None, db: int = 0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.db = db
        self._client: redis.Redis | None = None
        self._leases: dict[LockLease, RedisClientLock] = {}

    async def on_start(self, settings: Settings):
        client = redis.Redis(host=self.host, port=self.port, username=self.username, password=self.password, db=self.db,
                             decode_responses=True)

        await client.ping()

        self._client = client

    async def on_stop(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._leases.clear()

    @asynccontextmanager
    async def acquire(
            self,
            name: str,
            *,
            ttl_seconds: float = DEFAULT_LOCK_TTL_SECONDS,
            blocking_timeout_seconds: float = DEFAULT_BLOCKING_TIMEOUT_SECONDS,
    ) -> AsyncIterator[LockLease]:
        if self._client is None:
            raise RuntimeError("Service not started.")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Name must be a non-empty string.")

        if ttl_seconds <= 0:
            raise ValueError("TTL must be greater than zero seconds.")

        if blocking_timeout_seconds < 0:
            raise ValueError("Blocking timeout cannot be negative.")

        key = f"{_LOCK_KEY_PREFIX}{name}"

        lock = self._client.lock(
            key,
            timeout=ttl_seconds,
            blocking_timeout=blocking_timeout_seconds,
        )

        if not await lock.acquire():
            raise LockAcquisitionError(f"Unable to acquire lock {name} within the configured timeout.")

        lease = LockLease(key, self)

        self._leases[lease] = lock

        try:
            yield lease
        finally:
            try:
                await lock.release()
            except RedisClientLockError as e:
                raise LockOwnershipError(f"Can't release lock {name} because it is no longer owned.") from e
            finally:
                self._leases.pop(lease, None)

    async def locked(self, name: str) -> bool:
        if self._client is None:
            raise RuntimeError("Service not started.")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Name must be a non-empty string.")

        lock = self._client.lock(f"{_LOCK_KEY_PREFIX}{name}")

        return await lock.locked()

    async def owned(self, lease: LockLease) -> bool:
        if self._client is None:
            raise RuntimeError("Service not started.")

        lock = self._leases.get(lease)

        if lock is None:
            return False

        return await lock.owned()

    async def extend(self, lease: LockLease, additional_seconds: float) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        if additional_seconds <= 0:
            raise ValueError("Extension must be greater than zero seconds.")

        lock = self._leases.get(lease)

        if lock is None:
            raise LockOwnershipError("Can't extend a lock that is no longer owned.")

        try:
            await lock.extend(additional_seconds)
        except RedisClientLockError as e:
            raise LockOwnershipError("Can't extend a lock that is no longer owned.") from e
