import asyncio
import datetime
import functools
import mimetypes
import re
import signal
from asyncio import AbstractEventLoop
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Self

import httpx

from linksurf.backqueue import BackQueue
from linksurf.broker.base import Broker
from linksurf.common.models import URL
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.components.base import Component
from linksurf.components.downloader import Downloader
from linksurf.components.frontier import Frontier
from linksurf.components.parser import Parser
from linksurf.components.storage import Storage
from linksurf.events.bus import EventBus
from linksurf.events.listeners import Listener, BetterStackListener
from linksurf.events.listeners import LoggingListener
from linksurf.extensions import Extension, VisualizationExtension
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

        Only absolute HTTP/HTTPS URLs are extracted.
        """

        mime_type, _ = mimetypes.guess_type(path)

        if mime_type and not mime_type.startswith('text/'):
            raise Exception("Seed file should be a plain text file.")

        with open(path, "r") as file:
            return cls.extract(file)

    @classmethod
    def from_url(cls, url: URL) -> Self:
        """
        Reads all valid URLs from a remote plain text file. Ignores lines starting with a # for testing convenience.

        Only absolute HTTP/HTTPS URLs are extracted. Does not follow redirects.
        """

        if url.extension != "txt":
            raise Exception("Seed file should be a plain text file.")

        response = httpx.get(url.address, timeout=30.0)

        if not response.is_success:
            raise Exception(f"Seed file request failed with status code {response.status_code}.")

        return cls.extract(response.text.splitlines())

    @classmethod
    def extract(cls, lines: Iterable[str]) -> Self:
        URL_REGEX = "^https?:\\/\\/(?:www\\.)?[-a-zA-Z0-9@:%._\\+~#=]{1,256}\\.[a-zA-Z0-9()]{1,6}\\b(?:[-a-zA-Z0-9()@:%_\\+.~#?&\\/=]*)$"

        urls: list[str] = []

        for line in lines:
            if line.startswith("#"):
                continue

            matches = re.findall(URL_REGEX, line)

            urls.extend(matches)

        unique_urls = set(urls)

        return cls([URL(url) for url in unique_urls])


class Linksurf:
    identifier: str
    buckets: list[int]
    started_at: datetime

    def __init__(self, settings: Settings, services: Services, broker: Broker):
        self.identifier = get_env("IDENTIFIER")
        self.buckets = [int(b) for b in get_env("BUCKETS").split(",")]

        self.settings = settings
        self.services = services
        self.broker = broker
        self.back_queue = BackQueue()

        self.frontier = Frontier(broker)
        self.downloader = Downloader(broker, self.back_queue)
        self.parser = Parser(broker)
        self.storage = Storage(broker)

        self.components: list[Component] = [
            self.frontier,
            self.downloader,
            self.parser,
            self.storage,
        ]
        self.listeners: list[Listener] = [
            LoggingListener(),
            BetterStackListener(
                source_token=get_env("BETTERSTACK_SOURCE_TOKEN"),
                host=get_env("BETTERSTACK_HOST")
            )
        ]
        self.extensions: list[Extension] = [
            VisualizationExtension(self, self.settings, self.services),
        ]

    async def start(self, seed: Seed) -> None:
        Logger().info("application.start", identifier=self.identifier, buckets=self.buckets)

        self.started_at = datetime.now(timezone.utc)

        Logger().info("listeners.register", listeners=[type(listener).__name__ for listener in self.listeners])

        for listener in self.listeners:
            for name in listener.EVENTS:
                EventBus().on(name, listener.handle)

        def on_signal(sig, loop: AbstractEventLoop):
            Logger().info("application.shutdown", message="Press Ctrl+C to exit immediately.")

            self.broker.stop()

            self.back_queue.drain()

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

        Logger().info("extensions.start", extensions=[type(extension).__name__ for extension in self.extensions])

        for extension in self.extensions:
            await extension.on_start()

        self.back_queue.set_buckets(self.buckets)

        try:
            await self.back_queue.on_start(self.services)
        except:
            Logger().exception("back_queue.error", error="Back Queue startup failed.")

            await self.shutdown()

            return

        for component in self.components:
            await component.on_start(self.settings, self.services)

        await self.seed(seed.urls)

        Logger().info("broker.loop")

        try:
            await self.broker.loop()
        except Exception:
            Logger().exception("application.crash")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        for extension in self.extensions:
            try:
                await extension.on_stop()
            except:
                Logger().exception("extension.error", error="Extension stop failed.")
            else:
                Logger().info("extension.stop", extension=type(extension).__name__)

        for component in self.components:
            try:
                await component.on_stop()
            except:
                Logger().exception("component.error", error="Component stop failed.")
            else:
                Logger().info("component.stop", component=component.NAME)

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
