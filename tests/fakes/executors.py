from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from linksurf.common.payload import Payload
from linksurf.components.base import Deduplicator, Filter, Middleware, Prioritizer, Rule

Outcome = Any | BaseException | Callable[..., Any]
_UNSET = object()


class FakeExecutor:
    _UNTRACKED_FUNCTIONS = {
        "mock",
        "_record",
        "_resolve_async",
        "__getattribute__",
        "__init__",
    }

    def __init__(self) -> None:
        self.executions: list[Payload] = []
        self.calls: dict[str, int] = {}
        self._outcome: Outcome | object = _UNSET

    def __getattribute__(self, name: str):
        attribute = object.__getattribute__(self, name)
        untracked = object.__getattribute__(self, "_UNTRACKED_FUNCTIONS")

        if name in untracked or name.startswith("__") or not callable(attribute):
            return attribute

        if inspect.iscoroutinefunction(attribute):
            @wraps(attribute)
            async def tracked_async(*args, **kwargs):
                record = object.__getattribute__(self, "_record")
                record(name, args)

                outcome = object.__getattribute__(self, "_outcome")

                if name == "execute" and outcome is not _UNSET:
                    resolve = object.__getattribute__(self, "_resolve_async")

                    return await resolve(outcome, *args, **kwargs)

                return await attribute(*args, **kwargs)

            return tracked_async

        @wraps(attribute)
        def tracked_sync(*args, **kwargs):
            record = object.__getattribute__(self, "_record")

            record(name, args)

            return attribute(*args, **kwargs)

        return tracked_sync

    def mock(self, outcome: Outcome) -> None:
        """
        Set or replace the outcome returned by execute().
        """

        self._outcome = outcome

    async def on_start(self, settings, services) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    async def execute(self, payload: Payload):
        raise AssertionError("No outcome mocked for execute().")

    def _record(self, function: str, args: tuple[Any, ...]) -> None:
        self.calls[function] = self.calls.get(function, 0) + 1

        if function == "execute" and args and isinstance(args[0], Payload):
            self.executions.append(args[0])

    async def _resolve_async(self, outcome: Outcome, *args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome

        result = outcome(*args, **kwargs) if callable(outcome) else outcome

        if inspect.isawaitable(result):
            return await result

        return result


class FakeRule(FakeExecutor, Rule):
    pass


class FakeDeduplicator(FakeExecutor, Deduplicator):
    pass


class FakeMiddleware(FakeExecutor, Middleware):
    pass


class FakeFilter(FakeExecutor, Filter):
    DEPENDS_ON = []


class FakePrioritizer(FakeExecutor, Prioritizer):
    pass
