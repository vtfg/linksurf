from typing import Callable, Any

from linksurf.events import Event


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable[[Any], None]]] = {}

    def on(self, name: str, handler: Callable[[Any], None]) -> None:
        self._listeners.setdefault(name, []).append(handler)

    def emit(self, event: Event) -> None:
        for handler in self._listeners.get(event.name, []):
            handler(event)

        for handler in self._listeners.get("*", []):
            handler(event)
