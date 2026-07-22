import logging
import traceback
from dataclasses import asdict
from typing import Any

from logtail import LogtailHandler

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

        # real exception objects are rendered via exc_info
        # a plain string (e.g. RequestEvent's exception type path) is left in data as a normal field
        if isinstance(exception, BaseException):
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


class BetterStackListener(Listener):
    """
    Sends every event to BetterStack as a structured log via LogtailHandler,
    keeping all parameters for filtering and analysis.

    Only events explicitly logged here are sent.
    """

    EVENTS = ["*"]

    def __init__(self, source_token: str, host: str):
        handler = LogtailHandler(source_token=source_token, host=host)

        self._logger = logging.getLogger("linksurf.betterstack")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._logger.addHandler(handler)

    def handle(self, event: Event) -> None:
        exception = getattr(event, "exception", None)
        data = asdict(event)
        name = data.pop("name")

        # real exception objects get formatted into a traceback string
        # RequestEvent's exception field is already a plain string
        if isinstance(exception, BaseException):
            data["exception"] = "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__))

        level = logging.ERROR if name.endswith(".error") else logging.INFO

        self._logger.log(level, name, extra=data)
