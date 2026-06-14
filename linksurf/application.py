import signal

from linksurf.broker.base import Broker
from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.components.downloader import Downloader
from linksurf.components.frontier import Frontier
from linksurf.components.parser import Parser
from linksurf.components.storage import Storage
from linksurf.events.bus import EventBus
from linksurf.events.listeners import Listener
from linksurf.services import Services


class Linksurf:
    def __init__(self, settings: Settings, services: Services, broker: Broker):
        self.settings = settings
        self.services = services
        self.broker = broker
        self.event_bus = EventBus()

        self.frontier = Frontier()
        self.downloader = Downloader()
        self.parser = Parser()
        self.storage = Storage()

        self.listeners: list[Listener] = []

    def run(self, seed: list[URL]) -> None:
        for listener in self.listeners:
            for name in listener.EVENTS:
                self.event_bus.on(name, listener.handle)

        self.services.connect(self.settings)

        self.broker.connect()

        components = [self.frontier, self.downloader, self.parser, self.storage]

        for component in components:
            component.on_start(self.settings, self.services, self.event_bus)

        # Order don't matter. What matters is the component's CONSUMES_FROM and PRODUCES_TO.
        self.broker.pipeline(components)

        for url in seed:
            self.broker.seed(Frontier.CONSUMES_FROM, Payload(url=url))

        def shutdown(signum, frame):
            self.broker.stop()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        self.broker.loop()

        for component in components:
            component.on_stop()

        self.broker.disconnect()

        self.services.disconnect()
