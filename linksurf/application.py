import asyncio
import functools
import mimetypes
import re
import signal
from asyncio import AbstractEventLoop
from typing import Self

from linksurf.backqueue import BackQueue
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
        self.back_queue = BackQueue()

        self.frontier = Frontier(broker)
        self.downloader = Downloader(broker, self.back_queue)
        self.parser = Parser(broker)
        self.storage = Storage(broker)

        self.listeners: list[Listener] = [
            LoggingListener(),
            BetterStackListener(
                source_token=get_env("BETTERSTACK_SOURCE_TOKEN"),
                host=get_env("BETTERSTACK_HOST")
            )
        ]

    async def start(self, seed: Seed) -> None:
        for listener in self.listeners:
            for name in listener.EVENTS:
                EventBus().on(name, listener.handle)

        Logger().info("application.start")

        def on_signal(sig, loop: AbstractEventLoop):
            Logger().info("application.shutdown", message="Press Ctrl+C to exit immediately.")

            self.broker.stop()

            loop.remove_signal_handler(sig)

        loop = asyncio.get_event_loop()

        loop.add_signal_handler(signal.SIGINT, functools.partial(on_signal, signal.SIGINT, loop))
        loop.add_signal_handler(signal.SIGTERM, functools.partial(on_signal, signal.SIGTERM, loop))

        try:
            await self.broker.connect()
        except:
            Logger().exception("broker.error", error="Broker connection failed.")

            await self.shutdown()

            return
        else:
            Logger().info("broker.connect")

        try:
            await self.services.connect(self.settings)
        except:
            await self.shutdown()

            return

        components = [self.frontier, self.downloader, self.parser, self.storage]

        for component in components:
            await component.on_start(self.settings, self.services)

        await self.seed(seed.urls)

        try:
            await self.back_queue.on_start(self.services)
        except:
            Logger().exception("back_queue.error", error="Back Queue startup failed.")

            await self.shutdown()

            return

        Logger().info("broker.loop")

        try:
            await self.broker.loop()
        except Exception:
            Logger().exception("application.crash")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        components = [self.frontier, self.downloader, self.parser, self.storage]

        for component in components:
            await component.on_stop()

        try:
            await self.broker.disconnect()
        except:
            Logger().exception("broker.error", error="Broker disconnection failed.")
        else:
            Logger().info("broker.disconnect")

        await self.back_queue.on_stop()

        await self.services.disconnect()

        Logger().info("application.stop")

    async def seed(self, urls: list[URL]) -> None:
        Logger().info("application.seed", count=len(urls))

        for url in urls:
            payload = Payload(url)

            error = await self.frontier.process(payload)

            if error:
                Logger().error("application.error", message=f"Unable to seed URL.", url=url.address,
                               error=error.message)

                continue
