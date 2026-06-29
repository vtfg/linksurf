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
from linksurf.events.listeners import Listener, LoggingListener
from linksurf.logger import Logger
from linksurf.services import Services


class Linksurf:
    def __init__(self, settings: Settings, services: Services, broker: Broker):
        self.settings = settings
        self.services = services
        self.broker = broker

        self.frontier = Frontier(broker)
        self.downloader = Downloader(broker)
        self.parser = Parser(broker)
        self.storage = Storage(broker)

        self.listeners: list[Listener] = [
            LoggingListener(),
        ]

    def run(self, seed: list[URL]) -> None:
        for listener in self.listeners:
            for name in listener.EVENTS:
                EventBus().on(name, listener.handle)

        Logger().info("application.start")

        try:
            self.services.connect(self.settings)
        except:
            self.shutdown()

            return

        try:
            self.broker.connect()
        except:
            Logger().exception("broker.error", error="Broker connection failed.")

            self.shutdown()

            return

        Logger().info("broker.connect")

        components = [self.frontier, self.downloader, self.parser, self.storage]

        for component in components:
            component.on_start(self.settings, self.services)

        for url in seed:
            self.broker.seed(Frontier.TOPIC, Payload(url=url))

        def on_signal(signum, frame):
            Logger().info("application.shutdown")

            self.broker.stop()

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        self.broker.loop()

        self.shutdown()

    def shutdown(self) -> None:
        components = [self.frontier, self.downloader, self.parser, self.storage]

        for component in components:
            component.on_stop()

        try:
            self.broker.disconnect()
        except:
            Logger().exception("broker.error", error="Broker disconnection failed.")
        else:
            Logger().info("broker.disconnect")

        self.services.disconnect()

        Logger().info("application.stop")
