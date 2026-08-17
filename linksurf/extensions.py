from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import TYPE_CHECKING

import httpx

from linksurf.common.settings import Settings
from linksurf.events import Event
from linksurf.events.listeners import Listener
from linksurf.logger import Logger
from linksurf.services import Services, Service
from linksurf.utils.env import get_env

if TYPE_CHECKING:
    from linksurf.application import Linksurf


class Extension:
    """
    Increment the application's behavior by implementing new components, services and listeners,
    and also define new elements (rules, middlewares, filters, etc.) for the existing components.

    They serve as a drop-in behavior change that allows grouping related modifications in a single file.

    Extensions can be HTTP servers, like an Admin Panel that shows metrics about the crawler,
    or implement lifecycle events/scheduled events (e.g. to check proxies periodically).
    """

    # TODO: Create application callbacks so extensions can inject data into payloads or requests objects.
    # ^ Useful for user-agent rotation or proxy pool extensions.

    def __init__(self, application: Linksurf, settings: Settings, services: Services):
        """
        Function used to inject all components needed for the extension into the application.
        """

        self.application = application

    async def on_start(self):
        """
        Function used to start the extension and its required components (which were not injected).

        "Start" in this context means creating any database connection or requesting required data asynchronously, for example.
        """

        raise NotImplementedError()

    async def on_stop(self):
        """
        Function used to gracefully stop the extension and its required components (which were not injected).
        """

        raise NotImplementedError()


class VisualizationExtension(Extension):
    """
    Defines all components required for visualizing crawls in real-time.

    Used for project presentation only, as it reduces the overall performance by calling the Visualization API for every crawl event.

    Visualization is stored as a force-directed graph network. Each cluster represents a domain, and nodes its pages.
    The relationship follows the domain's directory structure. Root (`/`) at the center.
    """

    class VisualizationAPIClient(Service):
        """
        Sends crawl events to the Visualization API, which owns the graph and its database.

        Events are enqueued to delivery via a background worker, running whenever the crawler is waiting an I/O operation.
        """

        NAME = "VisualizationAPIClient"

        # dropping events is fine, the graph can be rebuilt from the Database
        MAX_PENDING_EVENTS = 10_000

        REQUEST_TIMEOUT_SECONDS = 5.0
        DRAIN_TIMEOUT_SECONDS = 30.0

        def __init__(self, url: str):
            super().__init__()

            self.url = url

            self._client: httpx.AsyncClient | None = None
            self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self.MAX_PENDING_EVENTS)
            self._worker: asyncio.Task | None = None

        async def on_start(self, settings: Settings):
            self._client = httpx.AsyncClient(base_url=self.url, timeout=self.REQUEST_TIMEOUT_SECONDS)

            try:
                response = await self._client.get("/api/health")

                response.raise_for_status()
            except Exception as e:
                await self._client.aclose()

                raise RuntimeError(f"Visualization API is unreachable.") from e

            self._worker = asyncio.create_task(self._send_queued())

        async def on_stop(self):
            if self._worker is not None:
                try:
                    await asyncio.wait_for(self._queue.join(), timeout=self.DRAIN_TIMEOUT_SECONDS)
                except TimeoutError:
                    Logger().warning("visualization.draining", pending=self._queue.qsize())

                self._worker.cancel()

            if self._client is not None:
                await self._client.aclose()

        def send(self, event: Event) -> None:
            """
            Queues an event for delivery. Returns immediately to release the task.
            """

            try:
                self._queue.put_nowait(asdict(event))
            except asyncio.QueueFull:
                Logger().warning("visualization.dropped", event=event.name)

        async def _send_queued(self) -> None:
            while True:
                payload = await self._queue.get()

                try:
                    response = await self._client.post("/api/event", json=payload)

                    if response.is_error:
                        Logger().warning("visualization.error", status_code=response.status_code,
                                         url=payload.get("url"))
                except Exception as e:
                    Logger().warning("visualization.error", message="Failed to send event.",
                                     exception=str(e))
                finally:
                    self._queue.task_done()

    class VisualizationListener(Listener):
        EVENTS = ["crawl.pending", "crawl.start", "crawl.finish"]

        def __init__(self, client: VisualizationExtension.VisualizationAPIClient):
            self.client = client

        async def handle(self, event: Event):
            self.client.send(event)

    def __init__(self, application: Linksurf, settings: Settings, services: Services):
        super().__init__(application, settings, services)

        self.client = self.VisualizationAPIClient(url=get_env("VISUALIZATION_API_URL"))
        self.listener = self.VisualizationListener(self.client)

        application.listeners.append(self.listener)
        application.services.register(self.client)

    async def on_start(self):
        pass

    async def on_stop(self) -> None:
        pass
