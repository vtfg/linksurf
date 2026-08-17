import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, NamedTuple, Awaitable

from linksurf.broker.base import Broker
from linksurf.common.models import ComponentExecution, CrawlStatus
from linksurf.common.payload import Payload
from linksurf.common.settings import Settings
from linksurf.common.types import Response, Error
from linksurf.events.bus import EventBus
from linksurf.logger import Logger
from linksurf.services import Services, Database


class Executor:
    async def on_start(self, settings: Settings, services: Services):
        pass

    async def on_stop(self):
        pass

    async def execute(self, payload: Payload):
        raise NotImplementedError()


class MiddlewareResponse(Response[Payload]):
    pass


# Enriches metadata
class Middleware(Executor):
    async def execute(self, payload: Payload) -> MiddlewareResponse:
        raise NotImplementedError()


class RuleResponse(Response[bool]):
    pass


class Rule(Executor):
    async def execute(self, payload: Payload) -> RuleResponse:
        raise NotImplementedError()


class FilterResponse(Response[bool]):
    pass


# Uses metadata to decide if URL should be skipped
class Filter(Executor):
    DEPENDS_ON: list[Middleware]

    async def execute(self, payload: Payload) -> FilterResponse:
        raise NotImplementedError()


class PrioritizerResponse(Response[int]):
    pass


class Prioritizer(Executor):
    async def execute(self, payload: Payload) -> PrioritizerResponse:
        raise NotImplementedError()


class DeduplicatorCheckResponse(NamedTuple):
    seen: bool | None
    error: Error | None


@dataclass
class DeduplicatorRegisterResponse:
    error: Error | None


class Deduplicator:
    async def on_start(self, settings: Settings, services: Services):
        pass

    async def on_stop(self):
        pass

    async def check(self, payload: Payload) -> DeduplicatorCheckResponse:
        raise NotImplementedError()

    async def register(self, payload: Payload) -> Error | None:
        raise NotImplementedError()

    async def unregister(self, payload: Payload) -> Error | None:
        raise NotImplementedError()


class Component:
    """
    Base class for the pipeline component.

    Defines functions for executing rules, deduplicators, middlewares, filters and prioritizers.
    Emits all base events automatically.
    """

    NAME: str
    FINAL: bool = False

    database: Database

    def __init__(self, broker: Broker) -> None:
        self.broker = broker

        self.rules: list[Rule] = []
        self.deduplicator: Deduplicator | None = None
        self.middlewares: list[Middleware] = []
        self.filters: list[Filter] = []
        self.prioritizer: Prioritizer | None = None

        if self.NAME is None:
            self.NAME = type(self).__name__

    async def on_start(self, settings: Settings, services: Services):
        self.database = services.database

        for rule in self.rules:
            await rule.on_start(settings, services)

        if self.deduplicator is not None:
            await self.deduplicator.on_start(settings, services)

        for middleware in self.middlewares:
            await middleware.on_start(settings, services)

        for filter in self.filters:
            await filter.on_start(settings, services)

        if self.prioritizer is not None:
            await self.prioritizer.on_start(settings, services)

    async def on_stop(self):
        for rule in self.rules:
            await rule.on_stop()

        if self.deduplicator is not None:
            await self.deduplicator.on_stop()

        for middleware in self.middlewares:
            await middleware.on_stop()

        for filter in self.filters:
            await filter.on_stop()

        if self.prioritizer is not None:
            await self.prioritizer.on_stop()

    async def rule(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Executes all rules. Returns True if the component should continue executing.
        """

        from linksurf.events import (
            RuleStartEvent, RuleFinishEvent, RuleErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        for rule in self.rules:
            rule_name = type(rule).__name__

            await EventBus().emit(
                RuleStartEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name))

            response = await rule.execute(payload)

            if response.error is not None:
                await EventBus().emit(
                    RuleErrorEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name,
                                   error=response.error.message, retriable=response.error.retriable,
                                   exception=response.error.exception))

                return None, response.error

            await EventBus().emit(
                RuleFinishEvent(correlation_id=correlation_id, url=url, component=component_name, rule=rule_name,
                                passed=bool(response.data)))

            if not response.data:
                return False, None

        return True, None

    async def deduplicate(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Checks if duplicate and registers if not.
        """

        if self.deduplicator is None:
            raise Exception("Deduplicator not defined.")

        if payload.deduplicated:
            # this payload was already deduplicated once; re-checking would only block its own retry

            Logger().debug("component.debug", component=self.NAME,
                           url=payload.url.address, message="Bypassing deduplication.")

            return False, None

        from linksurf.events import (
            DeduplicatorStartEvent, DeduplicatorFinishEvent, DeduplicatorErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__
        deduplicator_name = type(self.deduplicator).__name__

        await EventBus().emit(DeduplicatorStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                     deduplicator=deduplicator_name))

        response = await self.deduplicator.check(payload)

        if response.error is not None:
            await EventBus().emit(
                DeduplicatorErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                       deduplicator=deduplicator_name, error=response.error.message,
                                       retriable=response.error.retriable, exception=response.error.exception))

            return None, response.error

        if response.seen:
            await EventBus().emit(
                DeduplicatorFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        deduplicator=deduplicator_name, seen=True))

            payload.deduplicated = True

            return True, None

        error = await self.deduplicator.register(payload)

        if error is not None:
            await EventBus().emit(
                DeduplicatorErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                       deduplicator=deduplicator_name, error=error.message,
                                       retriable=error.retriable, exception=error.exception))

            return False, error

        payload.deduplicated = True

        await EventBus().emit(
            DeduplicatorFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                    deduplicator=deduplicator_name, seen=False))

        return False, None

    async def enrich(self, payload: Payload) -> Error | None:
        """
        Executes all middlewares. Updates payload in place.
        """

        from linksurf.events import (
            MiddlewareStartEvent, MiddlewareFinishEvent, MiddlewareErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        for middleware in self.middlewares:
            middleware_name = type(middleware).__name__
            metadata_snapshot = dict(payload.metadata)

            await EventBus().emit(MiddlewareStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                       middleware=middleware_name))

            response = await middleware.execute(payload)

            if response.error is not None:
                await EventBus().emit(
                    MiddlewareErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                         middleware=middleware_name,
                                         error=response.error.message,
                                         retriable=response.error.retriable,
                                         exception=response.error.exception))

                return response.error

            metadata_diff = {k: v for k, v in payload.metadata.items() if metadata_snapshot.get(k) != v}

            await EventBus().emit(
                MiddlewareFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                      middleware=middleware_name, data=metadata_diff))

        return None

    async def filter(self, payload: Payload) -> tuple[bool | None, Error | None]:
        """
        Executes all middlewares and filters. Returns True if the component should continue executing.
        """

        from linksurf.events import (
            FilterStartEvent, FilterFinishEvent, FilterErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__

        error = await self.enrich(payload)

        if error is not None:
            return None, error

        for filter in self.filters:
            filter_name = type(filter).__name__

            await EventBus().emit(
                FilterStartEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name))

            response = await filter.execute(payload)

            if response.error is not None:
                await EventBus().emit(
                    FilterErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                     filter=filter_name, error=response.error.message,
                                     retriable=response.error.retriable,
                                     exception=response.error.exception))

                return None, response.error

            await EventBus().emit(
                FilterFinishEvent(correlation_id=correlation_id, url=url, component=component_name, filter=filter_name,
                                  passed=bool(response.data)))

            if not response.data:
                return False, None

        return True, None

    async def prioritize(self, payload: Payload) -> tuple[int | None, Error | None]:
        """
        Calculates and returns a priority number.
        """

        if self.prioritizer is None:
            raise Exception("Prioritizer not defined.")

        from linksurf.events import (
            PrioritizerStartEvent, PrioritizerFinishEvent, PrioritizerErrorEvent,
        )

        correlation_id = payload.correlation_id
        url = payload.url.address
        component_name = type(self).__name__
        prioritizer_name = type(self.prioritizer).__name__

        await EventBus().emit(PrioritizerStartEvent(
            correlation_id=correlation_id, url=url,
            component=component_name, prioritizer=prioritizer_name,
        ))

        response = await self.prioritizer.execute(payload)

        if response.error is not None:
            await EventBus().emit(PrioritizerErrorEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
                error=response.error.message,
                retriable=response.error.retriable,
                exception=response.error.exception,
            ))

            return None, response.error

        if not response.data:
            error = Error("Prioritizer gave empty response.", retriable=True)

            await EventBus().emit(PrioritizerErrorEvent(
                correlation_id=correlation_id, url=url,
                component=component_name, prioritizer=prioritizer_name,
                error=error.message,
                retriable=error.retriable,
                exception=error.exception,
            ))

            return None, error

        await EventBus().emit(PrioritizerFinishEvent(
            correlation_id=correlation_id, url=url,
            component=component_name, prioritizer=prioritizer_name,
            priority=response.data,
        ))

        return response.data, None

    async def publish(self, topic: str, data: Payload | list[Payload]) -> None:
        from linksurf.events import ComponentPublishEvent

        payloads = data if isinstance(data, list) else [data]

        for payload in payloads:
            await self.broker.publish(topic, payload, payload.priority)

        await EventBus().emit(ComponentPublishEvent(
            component=self.NAME, topic=topic,
            urls=[(payload.url.address, payload.priority) for payload in payloads],
        ))

    async def _save_execution(self, payload: Payload, execution: ComponentExecution, error: Error | None) -> None:
        """
        Saves this component's execution into the payload's current crawl entry.

        A crawl is only created inside the Downloader, so the Frontier's execution details is discarded.
        """

        from linksurf.events import CrawlFinishEvent

        if error is not None:
            execution.error = error.message
            execution.retriable = error.retriable

            if error.exception is not None:
                exception_type = type(error.exception)
                execution.exception = f"{exception_type.__module__}.{exception_type.__qualname__}"

        if payload.crawl_id is None:
            return

        fields: dict[str, Any] = {"finished_at": execution.finished_at}

        if payload.request is not None:
            fields["request"] = asdict(payload.request)
        if payload.response is not None:
            fields["response"] = asdict(payload.response)
        if payload.content is not None:
            fields["content"] = asdict(payload.content)
        if payload.redirects:
            fields["redirects"] = [asdict(redirect) for redirect in payload.redirects]

        metadata = {key: value for key, value in payload.metadata.items() if key != "links"}

        if metadata:
            fields["metadata"] = metadata

        if error is not None:
            status = CrawlStatus.ERRORED
        elif payload.published:
            # payload was forwarded to the next pipeline stage
            status = CrawlStatus.IN_PROGRESS
        elif payload.response is not None and payload.response.is_redirect:
            # redirects in Downloader causes a crawl to stop and the new URL be sent to Frontier (if < MAX_REDIRECTS)
            status = CrawlStatus.REDIRECTED
        elif self.FINAL:
            # here can have an edge case when the final component early-exited
            # won't happen now because Storage has no filters, but gotta be careful
            status = CrawlStatus.SUCCEEDED
        else:
            # early-exit with no error
            # happens when a payload was filtered or deduplicated
            status = CrawlStatus.SKIPPED

        fields["status"] = status.value

        try:
            await self.database.update_crawl(payload.crawl_id, execution, fields)
        except Exception as e:
            Logger().error("component.error", component=self.NAME, message="Failed to save crawl execution.",
                           exception=str(e))

        if status != CrawlStatus.IN_PROGRESS:
            await EventBus().emit(
                CrawlFinishEvent(correlation_id=payload.correlation_id, id=payload.crawl_id, component=self.NAME,
                                 url=payload.url.address, status=status))


class ConsumerComponent(Component):
    """
    A component that consumes from the defined Broker topic and processes Payloads from it.
    """

    TOPIC: str

    async def subscribe(self, topic: str, callback: Callable[[Payload], Awaitable[Error | None]],
                        concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("Concurrency must be >= 1.")

        from linksurf.events import ComponentSubscribeEvent

        component_name = type(self).__name__

        await EventBus().emit(ComponentSubscribeEvent(component=component_name, topic=topic))

        async def handler(data: Payload):
            from linksurf.events import (
                ComponentStartEvent, ComponentFinishEvent, ComponentErrorEvent,
            )

            correlation_id = data.correlation_id
            url = data.url.address
            started_at = datetime.now(timezone.utc)
            start_time = time.perf_counter()

            if data.retrying:
                # increment before processing so events reflect the current retry count
                data.retries += 1

            await EventBus().emit(ComponentStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                                      topic=topic, retrying=data.retrying, retries=data.retries))

            try:
                error = await callback(data)
            except Exception as e:
                error = Error("Uncaught error.", exception=e, retriable=False, unexpected=True)

            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            finished_at = datetime.now(timezone.utc)

            execution = ComponentExecution(
                component=self.NAME,
                rules=[type(rule).__name__ for rule in self.rules],
                deduplicator=type(self.deduplicator).__name__ if self.deduplicator else None,
                middlewares=[type(middleware).__name__ for middleware in self.middlewares],
                filters=[type(filter).__name__ for filter in self.filters],
                retries=data.retries,
                started_at=started_at,
                finished_at=finished_at,
            )

            if error is not None:
                await EventBus().emit(
                    ComponentErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        error=error.message,
                                        retriable=error.retriable,
                                        retrying=data.retrying,
                                        retries=data.retries,
                                        unexpected=error.unexpected,
                                        exception=error.exception))
            else:
                await EventBus().emit(
                    ComponentFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                         topic=topic, duration_ms=duration_ms,
                                         retrying=data.retrying, retries=data.retries))

            await self._save_execution(data, execution, error)

        await self.broker.subscribe(topic, handler, concurrency=concurrency)


class LooperComponent(Component):
    """
    A component that loops a defined callback indefinitely.

    Requires a `pull` function, which is responsible for gathering Payloads to process.
    """

    def __init__(self, broker: Broker) -> None:
        super().__init__(broker)

        self._looping = False
        self._loop_tasks: list[asyncio.Task] = []
        self._loop_in_flight: set[asyncio.Task] = set()

    async def on_stop(self) -> None:
        self._looping = False

        if self._loop_in_flight:
            Logger().warning("component.draining", component=self.NAME, pending=len(self._loop_in_flight))

            await asyncio.gather(*self._loop_in_flight, return_exceptions=True)

        self._loop_tasks = []
        self._loop_in_flight = set()

        await super().on_stop()

    async def loop(self, pull: Callable[[], Awaitable[tuple[Payload, Any]]],
                   callback: Callable[[Payload, ...], Awaitable[Error | None]],
                   concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("Concurrency must be >= 1.")

        from linksurf.events import (
            ComponentLoopEvent, ComponentStartEvent, ComponentFinishEvent, ComponentErrorEvent
        )

        component_name = type(self).__name__
        function_name = callback.__name__

        await EventBus().emit(ComponentLoopEvent(component=component_name, function=function_name))

        self._looping = True

        async def handler():
            while self._looping:
                try:
                    payload, *extra = await pull()
                except Exception:
                    Logger().exception("component.pull_error", component=component_name, function=function_name)

                    continue

                correlation_id = payload.correlation_id
                url = payload.url.address
                started_at = datetime.now(timezone.utc)
                start_time = time.perf_counter()

                if payload.retrying:
                    payload.retries += 1

                task = asyncio.current_task()
                self._loop_in_flight.add(task)

                await EventBus().emit(
                    ComponentStartEvent(correlation_id=correlation_id, url=url, component=component_name,
                                        function=function_name, retrying=payload.retrying,
                                        retries=payload.retries))

                try:
                    error = await callback(payload, *extra)
                except Exception as e:
                    error = Error("Uncaught error.", exception=e, retriable=False, unexpected=True)

                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                finished_at = datetime.now(timezone.utc)

                execution = ComponentExecution(
                    component=self.NAME,
                    rules=[type(rule).__name__ for rule in self.rules],
                    deduplicator=type(self.deduplicator).__name__ if self.deduplicator else None,
                    middlewares=[type(middleware).__name__ for middleware in self.middlewares],
                    filters=[type(filter).__name__ for filter in self.filters],
                    retries=payload.retries,
                    started_at=started_at,
                    finished_at=finished_at,
                )

                if error is not None:
                    await EventBus().emit(
                        ComponentErrorEvent(correlation_id=correlation_id, url=url, component=component_name,
                                            error=error.message,
                                            retriable=error.retriable,
                                            retrying=payload.retrying,
                                            retries=payload.retries,
                                            unexpected=error.unexpected,
                                            exception=error.exception))
                else:
                    await EventBus().emit(
                        ComponentFinishEvent(correlation_id=correlation_id, url=url, component=component_name,
                                             function=function_name, duration_ms=duration_ms,
                                             retrying=payload.retrying, retries=payload.retries))

                await self._save_execution(payload, execution, error)

                self._loop_in_flight.discard(task)

        self._loop_tasks = [asyncio.create_task(handler()) for _ in range(concurrency)]


class SchedulerComponent(Component):
    """
    This type of component executes a callback from time to time, respecting a CRON expression.
    Doesn't receive Payloads for processing, but may gather and publish to consumer components.

    Can be useful for background data analysis or re-crawl scheduling (the intended use).
    """

    async def schedule(self, cron: str, callback: Callable[[], Awaitable]):
        raise NotImplementedError()
