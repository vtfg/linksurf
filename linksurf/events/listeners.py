from dataclasses import asdict
from typing import Any

from linksurf.events import Event
from linksurf.logger import Logger

MAX_LOGGED_LIST_ITEMS = 3


def _truncate_list(value: Any) -> Any:
    if isinstance(value, list) and len(value) > MAX_LOGGED_LIST_ITEMS:
        remaining = len(value) - MAX_LOGGED_LIST_ITEMS

        return [*value[:MAX_LOGGED_LIST_ITEMS], f"(+{remaining})"]

    return value


class Listener:
    EVENTS: list[str] = ["*"]

    def handle(self, event: Event) -> None:
        pass


class LoggingListener(Listener):
    EVENTS = ["*"]

    def handle(self, event: Event) -> None:
        exception = getattr(event, "exception", None)
        data = asdict(event)
        name = data.pop("name")
        data.pop("correlation_id", None)
        data.pop("exception", None)

        data = {key: _truncate_list(value) for key, value in data.items()}

        if name.endswith(".error"):
            exc_info = None

            # all executors' errors are also returned from the component,
            # this validation exists so it only logs the traceback once
            if name == "component.error":
                exc_info = (type(exception), exception, exception.__traceback__) if exception else None

            Logger().error(name, exc_info=exc_info, **data)
        else:
            Logger().info(name, **data)
