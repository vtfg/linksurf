import mimetypes
import re
import signal
from typing import Self

from linksurf.broker.base import Broker
from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.components.downloader import Downloader
from linksurf.components.frontier import Frontier
from linksurf.components.parser import Parser
from linksurf.components.storage import Storage
from linksurf.events.bus import EventBus
from linksurf.events.listeners import Listener, LoggingListener, BetterStackListener
from linksurf.logger import Logger
from linksurf.services import Services
from linksurf.utils.env import get_env


class Seed:
    def __init__(self, urls: list[URL]) -> None:
        self.urls = urls

    @classmethod
    def from_file(cls, path: str) -> Self:
        """
        Reads all valid URLs from a plain text file. Ignores lines starting with a # for testing convenience.

        Only HTTP/HTTPS URLs are supported.
        """

        mime_type, _ = mimetypes.guess_type(path)

        if mime_type and not mime_type.startswith('text/'):
            raise Exception(f"Seed file should be a plain text file.")

        urls: list[str] = []

        url_regex = "^https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)$"

        with open(path, "r") as file:
            for line in file:
                if line.startswith("#"):
                    continue

                matches = re.findall(url_regex, line)

                urls.extend(matches)

        unique_urls = set(urls)

        return cls([URL(url) for url in unique_urls])


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
            BetterStackListener(
                source_token=get_env("BETTERSTACK_SOURCE_TOKEN"),
                host=get_env("BETTERSTACK_HOST")
            )
        ]

    def run(self, seed: Seed) -> None:
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

        Logger().info("broker.seed", count=len(seed.urls))

        for url in seed.urls:
            self.broker.seed(Frontier.TOPIC, Payload(url=url))

        def on_signal(signum, frame):
            Logger().info("application.shutdown")

            self.broker.stop()

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        Logger().info("broker.loop")

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
