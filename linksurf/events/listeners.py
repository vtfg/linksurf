from dataclasses import asdict

from linksurf.events import Event
from linksurf.logger import Logger


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
        data.pop("exception", None)

        if name.endswith(".error"):
            exc_info = None

            # all executors' errors are also returned from the component,
            # this validation exists so it only logs the traceback once
            if name == "component.error":
                exc_info = (type(exception), exception, exception.__traceback__) if exception else None

            Logger().error(name, exc_info=exc_info, **data)
        else:
            Logger().info(name, **data)
