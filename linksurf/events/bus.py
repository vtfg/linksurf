from __future__ import annotations

from typing import Callable, Awaitable

from linksurf.events import Event
from linksurf.logger import Logger


class EventBus:
    _instance: EventBus = None

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._listeners: dict[str, list[Callable[[Event], Awaitable[None]]]] = {}

        return cls._instance

    def on(self, name: str, handler: Callable[[Event], Awaitable[None]]) -> None:
        self._listeners.setdefault(name, []).append(handler)

    async def emit(self, event: Event) -> None:
        for handler in self._listeners.get(event.name, []) + self._listeners.get("*", []):
            try:
                await handler(event)
            except Exception:
                listener = type(getattr(handler, "__self__", handler))

                Logger().exception("listener.error", listener=listener.__name__)
