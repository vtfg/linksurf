from __future__ import annotations

from typing import Callable, Any

from linksurf.events import Event


class EventBus:
    _instance: EventBus | None = None

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._listeners: dict[str, list[Callable[[Any], None]]] = {}

        return cls._instance

    def on(self, name: str, handler: Callable[[Any], None]) -> None:
        self._listeners.setdefault(name, []).append(handler)

    def emit(self, event: Event) -> None:
        for handler in self._listeners.get(event.name, []):
            handler(event)

        for handler in self._listeners.get("*", []):
            handler(event)
