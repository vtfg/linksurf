from asyncio import Lock
from urllib.parse import urljoin

from linksurf.backqueue import BackQueue
from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_REDIRECT_DEPTH, TEN_MEGABYTES_IN_BYTES
from linksurf.common.models import (
    Crawl,
    HTTPRequest,
    HTTPRequestMetadata,
    MimeType,
    Redirect,
    CrawlStatus,
    URL,
    HTTPResponse,
)
from linksurf.common.payload import Content, Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import LooperComponent
from linksurf.components.downloader.filters import ContentTypeFilter, ContentLengthFilter
from linksurf.components.downloader.middlewares import ContentTypeMiddleware, ContentLengthMiddleware
from linksurf.events import CrawlStartEvent
from linksurf.events.bus import EventBus
from linksurf.services import Services, Fetcher, BlobStorage, Cache, Database


class Downloader(LooperComponent):
    NAME = "Downloader"

    back_queue: BackQueue

    database: Database
    blob_storage: BlobStorage
    cache: Cache
    fetcher: Fetcher

    def __init__(self, broker: Broker, back_queue: BackQueue):
        super().__init__(broker)

        self.back_queue = back_queue

        self.middlewares = [
            ContentTypeMiddleware(),
            ContentLengthMiddleware(),
        ]
        self.filters = [
            ContentTypeFilter(allowed=[MimeType.HTML]),
            ContentLengthFilter(max_bytes=TEN_MEGABYTES_IN_BYTES),
        ]

    async def on_start(self, settings: Settings, services: Services):
        await super().on_start(settings, services)

        self.database = services.database
        self.blob_storage = services.blob_storage
        self.cache = services.cache
        self.fetcher = services.fetcher

        await self.loop(self.back_queue.next, self.download, concurrency=20)

    async def download(self, payload: Payload, lock: Lock) -> Error | None:
        if payload.crawl_id is None:
            crawl = Crawl(status=CrawlStatus.IN_PROGRESS)

            try:
                await self.database.start_crawl(payload.url.hash, crawl)
            except Exception as e:
                return Error("Database write failed.", retriable=True, exception=e)

            payload.crawl_id = crawl.id

            await EventBus().emit(
                CrawlStartEvent(correlation_id=payload.correlation_id, id=crawl.id, component=self.NAME,
                                url=payload.url.address))

        async with lock:
            request = HTTPRequest(
                url=payload.url.address, follow_redirects=False,
                metadata=HTTPRequestMetadata(correlation_id=payload.correlation_id, component="Downloader")
            )

            payload.request = request.to_summary()

            response: HTTPResponse | None = None
            exception: Exception | None = None

            try:
                response = await self.fetcher.http(request)
            except Exception as e:
                exception = e

                return Error("HTTP fetch failed.", retriable=True, exception=e)
            finally:
                await self.back_queue.report(payload, response, exception=exception)

        if response is None:
            return Error("HTTP fetch returned empty response.", retriable=True)

        payload.response = response.to_summary()

        if response.is_redirect:
            return await self._handle_redirect(payload, response, request)

        if not response.ok:
            return Error(f"Response has unacceptable status ({response.status_code}).", retriable=False)

        proceed, error = await self.filter(payload)

        if error is not None:
            return error

        if not proceed:
            return None

        content_type = payload.get_metadata("content_type")
        key = f"{payload.url.hash}/{payload.crawl_id}"

        try:
            await self.blob_storage.upload(response.body, key, content_type=content_type)
        except Exception as e:
            return Error("Blob upload failed.", retriable=True, exception=e)

        try:
            mime_type = MimeType(content_type)
        except ValueError:
            mime_type = MimeType.UNKNOWN

        payload.content = Content(key=key, type=mime_type)

        payload.published = True

        await self.publish("url.parse", payload)

        return None

    async def _handle_redirect(self, payload: Payload, response: HTTPResponse, request: HTTPRequest) -> Error | None:
        """
        Records this hop's response and, if under the depth limit, publishes the redirect target back to the Frontier.

        Current crawl ends here with status REDIRECTED (or ERRORED, if the depth limit was hit).
        """

        location = response.headers.get("location")

        if not location:
            return Error("Redirect response missing a Location header.", retriable=False)

        target = URL(urljoin(payload.url.address, location))

        payload.redirects.append(Redirect(
            source=payload.url.address, target=target.address,
            status_code=response.status_code, depth=len(payload.redirects),
        ))

        if payload.redirects[-1].depth >= MAX_REDIRECT_DEPTH:
            return Error("Redirect depth limit exceeded.", retriable=False)

        redirect_payload = Payload(url=target, redirects=payload.redirects)

        await self.publish("url.process", redirect_payload)

        return None
