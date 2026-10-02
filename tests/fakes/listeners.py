from linksurf.events import Event
from linksurf.events.listeners import Listener


# TODO: Allow asserting event data
class FakeListener(Listener):
    EVENTS = ["*"]

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def handle(self, event: Event) -> None:
        self.calls[event.name] = self.calls.get(event.name, 0) + 1
