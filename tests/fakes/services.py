from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from linksurf.services import BlobStorage, Cache, Database, Fetcher, Lock


Result = Any | BaseException | Callable[..., Any]


class FakeService:
    _UNTRACKED_FUNCTIONS = {
        "mock",
        "_record",
        "_resolve_async",
        "_resolve_sync",
        "__getattribute__",
        "__init__",
    }

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self._results: dict[str, Result] = {}

    def __getattribute__(self, name: str):
        attribute = object.__getattribute__(self, name)
        untracked = object.__getattribute__(self, "_UNTRACKED_FUNCTIONS")

        if name in untracked or name.startswith("__") or not callable(attribute):
            return attribute

        if inspect.iscoroutinefunction(attribute):
            @wraps(attribute)
            async def tracked_async(*args, **kwargs):
                record = object.__getattribute__(self, "_record")
                record(name)

                results = object.__getattribute__(self, "_results")
                if name in results:
                    resolve = object.__getattribute__(self, "_resolve_async")

                    return await resolve(results[name], *args, **kwargs)

                return await attribute(*args, **kwargs)

            return tracked_async

        @wraps(attribute)
        def tracked_sync(*args, **kwargs):
            record = object.__getattribute__(self, "_record")
            record(name)

            results = object.__getattribute__(self, "_results")
            if name in results:
                resolve = object.__getattribute__(self, "_resolve_sync")

                return resolve(results[name], *args, **kwargs)

            return attribute(*args, **kwargs)

        return tracked_sync

    def mock(self, function: str, result: Result) -> None:
        """Set or replace the result returned by a service function."""

        attribute = object.__getattribute__(self, function)

        if not callable(attribute):
            raise TypeError(f"{function!r} is not a function.")

        self._results[function] = result

    async def on_start(self, settings) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    def _record(self, function: str) -> None:
        self.calls[function] = self.calls.get(function, 0) + 1

    async def _resolve_async(self, result: Result, *args, **kwargs):
        if isinstance(result, BaseException):
            raise result

        value = result(*args, **kwargs) if callable(result) else result

        if inspect.isawaitable(value):
            return await value

        return value

    def _resolve_sync(self, result: Result, *args, **kwargs):
        if isinstance(result, BaseException):
            raise result

        value = result(*args, **kwargs) if callable(result) else result

        if inspect.isawaitable(value):
            raise TypeError("A synchronous function cannot use an asynchronous mocked result.")

        return value


class FakeDatabase(FakeService, Database):
    pass


class FakeBlobStorage(FakeService, BlobStorage):
    pass


class FakeCache(FakeService, Cache):
    pass


class FakeFetcher(FakeService, Fetcher):
    pass


class FakeLock(FakeService, Lock):
    pass
