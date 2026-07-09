import asyncio
import time

from linksurf.broker.base import Broker
from linksurf.common.constants import MAX_REDIRECT_DEPTH, TEN_MEGABYTES_IN_BYTES
from linksurf.common.models import HTTPRequest, MimeType, Redirect, URL
from linksurf.common.payload import Content, Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Error
from linksurf.components.base import Component
from linksurf.components.downloader.filters import ContentTypeFilter, ContentLengthFilter
from linksurf.components.downloader.middlewares import ContentTypeMiddleware, ContentLengthMiddleware
from linksurf.logger import Logger
from linksurf.services import Services, Fetcher, BlobStorage, Cache
from linksurf.services.fetcher import MaxRedirectsError


class Downloader(Component):
    TOPIC = "url.download"

    blob_storage: BlobStorage
    cache: Cache
    fetcher: Fetcher

    def __init__(self, broker: Broker):
        super().__init__(broker)

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

        self.blob_storage = services.blob_storage
        self.cache = services.cache
        self.fetcher = services.fetcher

        await self.subscribe(self.TOPIC, self.download)

    async def download(self, payload: Payload) -> Error | None:
        error = await self.throttle(payload)

        if error is not None:
            return error

        request = HTTPRequest(url=payload.url.address, follow_redirects=True)

        try:
            response = await self.fetcher.http(request)
        except MaxRedirectsError as e:
            return Error("Too many redirects.", retriable=False, exception=e)
        except Exception as e:
            return Error("HTTP fetch failed.", retriable=True, exception=e)

        if response is None:
            return Error("HTTP fetch returned empty response.", retriable=True)

        if not response.ok:
            return Error(f"Response has unacceptable status ({response.status_code}).", retriable=False)

        if response.redirects:
            self._append_redirects(payload, response.redirects)

        if payload.redirects and payload.redirects[-1].depth >= MAX_REDIRECT_DEPTH:
            return Error("Redirect depth limit exceeded.", retriable=False)

        final_url = URL(response.url)

        if final_url.domain != payload.url.domain:
            redirect_payload = Payload(url=final_url, redirects=payload.redirects)

            await self.publish("url.process", redirect_payload)

            return None

        payload.url = final_url
        payload.response = response.to_summary()

        proceed, error = await self.filter(payload)

        if error is not None:
            return error

        if not proceed:
            return None

        mime_type = payload.get_metadata("content_type")
        key = payload.url.hash

        try:
            await self.blob_storage.upload(response.body, key, content_type=mime_type)
        except Exception as e:
            return Error("Blob upload failed.", retriable=True, exception=e)

        try:
            type = MimeType(mime_type)
        except ValueError:
            type = MimeType.UNKNOWN

        payload.content = Content(key=key, type=type)
        payload.request = request.to_summary()

        await self.publish("url.parse", payload)

        return None

    async def throttle(self, payload: Payload, delay: float = 1.0) -> Error | None:
        """
           Enforces per-domain crawl delays. Uses the Crawl-delay from robots.txt when
           available, falling back to `delay` from parameters.
           """

        domain = payload.url.domain
        port = payload.url.port

        robots = payload.get_metadata("robots") or {}
        delay = robots.get("delay") or delay

        try:
            last_fetch = await self.cache.get_domain_last_fetch(domain, port)
        except Exception as e:
            return Error("Cache lookup failed.", retriable=True, exception=e)

        if last_fetch is not None:
            elapsed = time.monotonic() - last_fetch

            if elapsed < delay:
                Logger().debug("component.debug", message=f"Sleeping for {delay - elapsed} seconds")

                await asyncio.sleep(delay - elapsed)

        try:
            await self.cache.save_domain_last_fetch(domain, port, time.monotonic())
        except Exception as e:
            return Error("Cache write failed.", retriable=True, exception=e)

        return None

    def _append_redirects(self, payload: Payload, redirects: list) -> None:
        # depth needs to be recalculated because the payload can already have an existing redirects fields
        # happens when cross-domain redirect, a new payload gets sent back to the Frontier and Downloader execution stops

        start_depth = len(payload.redirects)

        for i, redirect in enumerate(redirects):
            payload.redirects.append(Redirect(
                source=redirect.source,
                target=redirect.target,
                status_code=redirect.status_code,
                depth=start_depth + i,
            ))
