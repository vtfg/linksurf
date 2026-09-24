import asyncio
import functools
import mimetypes
import re
import signal
from asyncio import AbstractEventLoop
from collections.abc import Iterable
from dataclasses import asdict
from typing import Self

import httpx

from linksurf.backqueue import BackQueue
from linksurf.broker.base import Broker
from linksurf.common.constants import SHUTDOWN_DRAIN_TIMEOUT_SECONDS, HEARTBEAT_INTERVAL_SECONDS
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
from linksurf.services.lock import LockAcquisitionError
from linksurf.utils.env import get_env
from linksurf.worker import Worker


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
    def __init__(self, settings: Settings, services: Services, broker: Broker):
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

        self.worker = Worker(
            self.services,
            self.back_queue,
            metadata={
                "settings": asdict(settings),
                "extensions": [type(extension).__name__ for extension in self.extensions],
                "components": [component.NAME for component in self.components],
            },
        )

        EventBus().set_metadata({"worker": self.worker.identifier})

        self._heartbeat_task: asyncio.Task | None = None
        self._coordination_task: asyncio.Task | None = None
        self.stopping = False

    async def start(self, seed: Seed) -> None:
        Logger().info("application.start", identifier=self.worker.identifier)

        Logger().info("listeners.register", listeners=[type(listener).__name__ for listener in self.listeners])

        for listener in self.listeners:
            for name in listener.EVENTS:
                EventBus().on(name, listener.handle)

        def on_signal(sig, loop: AbstractEventLoop):
            Logger().info("application.shutdown", message="Press Ctrl+C to exit immediately.")

            self.worker.mark_draining()

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

        # Membership renewal must continue even when startup reconciliation is
        # waiting for the bucket coordination lock.
        self._heartbeat_task = asyncio.create_task(self.heartbeat())

        Logger().info("extensions.start", extensions=[type(extension).__name__ for extension in self.extensions])

        for extension in self.extensions:
            await extension.on_start()

        try:
            await self.worker.on_start()
        except:
            Logger().exception("worker.error", error="Worker startup failed.")

            await self.shutdown()

            return

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
        if self.stopping:
            return

        self.stopping = True

        release_worker = self.services.ready and not self.back_queue.ready

        if self.services.ready and self.back_queue.ready:
            # The signal handler normally starts draining. This fallback also
            # prevents new local admission after an unexpected broker exit.
            self.worker.mark_draining()

            try:
                # updates the Worker's status immediately
                await self.worker.upsert()
            except Exception:
                Logger().exception("worker.error", error="Failed to publish draining state.")

            drained = await self.back_queue.wait_for_drain(SHUTDOWN_DRAIN_TIMEOUT_SECONDS)

            if drained:
                release_worker = True
            else:
                Logger().warning(
                    "application.shutdown_timeout",
                    message="Local queue did not drain; bucket leases will expire naturally.",
                )

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
            self._heartbeat_task = None

        if self._coordination_task is not None:
            self._coordination_task.cancel()

            await asyncio.gather(self._coordination_task, return_exceptions=True)

            self._coordination_task = None

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

        if self.back_queue.ready:
            await self.back_queue.on_stop()

        if release_worker:
            await self.worker.on_stop()

        if self.services.ready:
            await self.services.disconnect()

        Logger().info("application.stop")

    async def seed(self, urls: list[URL]) -> None:
        lock = self.services.lock

        try:
            async with lock.acquire("seed", ttl_seconds=5 * 60, blocking_timeout_seconds=5):
                Logger().info("application.seed", message="Seeding using the broker.", count=len(urls))

                for url in urls:
                    payload = Payload(url)

                    try:
                        await self.broker.seed(self.frontier.TOPIC, payload)
                    except:
                        Logger().exception("application.error", error="Unable to seed URL.", url=url.address)
        except LockAcquisitionError:
            Logger().info("application.seed", message="Another worker is already seeding.")

    async def heartbeat(self) -> None:
        """
        Refresh worker membership independently from bucket coordination.
        """

        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

                try:
                    # TODO: Validate services and broker readiness, shutdown otherwise

                    await self.worker.upsert()

                    Logger().info("application.heartbeat", status=self.worker.status)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    Logger().exception("application.heartbeat_error")

                    continue

                if (
                        not self.stopping
                        and self.back_queue.ready
                        and (self._coordination_task is None or self._coordination_task.done())
                ):
                    self._coordination_task = asyncio.create_task(self.coordinate())
        except asyncio.CancelledError:
            return

    async def coordinate(self) -> None:
        try:
            await self.worker.coordinate()
        except asyncio.CancelledError:
            raise
        except Exception:
            Logger().exception("application.coordination_error")
