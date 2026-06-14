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
        data = asdict(event)
        name = data.pop("name")

        if name.endswith(".error"):
            Logger().error(name, **data)
        else:
            Logger().info(name, **data)
