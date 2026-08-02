from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from linksurf.common.constants import MAX_DOMAIN_CONSECUTIVE_LOCKS, MAX_CRAWL_HISTORY_PER_URL
from linksurf.common.models import Crawl, ComponentExecution
from linksurf.common.settings import Settings
from linksurf.services.base import Service


class DomainStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    BLOCKED = "blocked"


@dataclass
class DomainMetrics:
    # counter of content languages identified by the LanguageMiddleware
    # only populated by the LanguageFilter
    languages: dict[str, int] = field(default_factory=dict)


@dataclass
class DomainModel:
    domain: str
    status: DomainStatus = DomainStatus.ACTIVE
    lock_count: int = 0
    locked_until: datetime | None = None
    blocked_at: datetime | None = None
    blocked_reason: str | None = None
    last_locked_at: datetime | None = None
    metrics: DomainMetrics = field(default_factory=DomainMetrics)


@dataclass
class URLModel:
    address: str
    hash: str
    domain: str
    priority: int
    correlation_id: str
    crawls: list[Crawl] = field(default_factory=list)
    # ^ contains only the last MAX_CRAWL_HISTORY_PER_URL entries
    # empty list means the Frontier registered this URL but the Downloader didn't attempted to fetch yet
    # current state (status, request, response, content, redirects, metadata) is read from crawls[-1]
    discovered_at: datetime = datetime.now(timezone.utc)


class Database(Service):
    NAME = "database"

    async def register_url(self, url: URLModel) -> None:
        """
        Save a URL to the database.

        Doesn't upsert to prevent state loss.
        """

        raise NotImplementedError()

    async def start_crawl(self, hash: str, crawl: Crawl) -> None:
        """
        Appends a `crawl` entry as the newest entry for the URL document identified by `hash`,
        bounded to the last MAX_CRAWL_HISTORY_PER_URL.

        Ensures the document exist first.
        """

        raise NotImplementedError()

    async def update_crawl(self, crawl_id: str, execution: ComponentExecution,
                           fields: dict[str, Any]) -> None:
        """
        Records a component `execution` entry into the crawl identified by `crawl_id`, overwriting any existing
        entry for the same component (only happens on retries).

        The `fields` dict applies patches to the crawl-level attributes (request, response, content, redirects, etc.).
        """

        raise NotImplementedError()

    async def save_domain(self, domain: str) -> None:
        """
        Ensures a domain record exists, creating one with active status if it doesn't already exist yet.
        Doesn't overwrite existing lock state.
        """

        raise NotImplementedError()

    async def get_distinct_domains(self, excluded: list[str], limit: int) -> list[str]:
        """
        Queries and returns a list of N (`limit`) distinct domains, excluding those in `excluded`.

        Domains are ordered by average pending URLs' priority.
        """

        raise NotImplementedError()

    async def get_domain_urls(self, domain: str, limit: int) -> list[URLModel]:
        """
        Gets a list of N (`limit`) never crawled URLs for a domain after ordering by priority.
        """

        raise NotImplementedError()

    async def get_excluded_domains(self) -> list[str]:
        """
        Returns domains that shouldn't be crawled right now: permanently blocked ones, and
        temporarily locked ones still within their lock window.
        """

        raise NotImplementedError()

    async def lock_domain(self, domain: str, until: datetime, reason: str) -> DomainStatus:
        """
        Registers a lock-triggering failure for a domain, incrementing its consecutive lock
        count. Escalates to a permanent block once MAX_DOMAIN_CONSECUTIVE_LOCKS is reached.

        Returns the domain's resulting status.
        """

        raise NotImplementedError()

    async def unlock_domain(self, domain: str) -> None:
        """
        Resets a domain's consecutive lock count back to zero after a non-locking request.
        """

        raise NotImplementedError()

    async def record_language(self, domain: str, language: str, allowed: bool,
                              threshold: int = 5) -> DomainStatus | None:
        """
        Increments the domain's page count for a language.
        
        Blocks the domain if language isn't allowed and its count reaches the defined threshold.
        """

        raise NotImplementedError()


class MongoDatabase(Database):
    _client: AsyncMongoClient | None
    _database: AsyncDatabase | None

    def __init__(self, url: str, name: str = "linksurf"):
        self.uri = url
        self.name = name

    async def on_start(self, settings: Settings):
        self._client = AsyncMongoClient(self.uri)
        self._database = self._client[self.name]

        await self._client.aconnect()

    async def on_stop(self):
        if self._client is not None:
            await self._client.aclose()
            self._database = None
            self._client = None

    async def register_url(self, url: URLModel) -> None:
        if self._client is None or self._database is None:
            raise RuntimeError("Service not started.")

        await self._database["urls"].update_one(
            {"hash": url.hash},
            {"$setOnInsert": asdict(url)},
            upsert=True,
        )

    async def start_crawl(self, hash: str, crawl: Crawl) -> None:
        if self._client is None or self._database is None:
            raise RuntimeError("Service not started.")

        document = await self._database["urls"].find_one({"hash": hash})

        if document is None:
            raise ValueError(f"No URL document found for hash {hash}.")

        crawls = document["crawls"] + [asdict(crawl)]
        crawls = crawls[-MAX_CRAWL_HISTORY_PER_URL:]

        await self._database["urls"].update_one(
            {"hash": hash},
            {"$set": {"crawls": crawls}},
        )

    async def update_crawl(self, crawl_id: str, execution: ComponentExecution, fields: dict[str, Any]) -> None:
        if self._client is None or self._database is None:
            raise RuntimeError("Service not started.")

        document = await self._database["urls"].find_one({"crawls.id": crawl_id})

        if document is None:
            return

        execution_data = asdict(execution)

        for crawl in document["crawls"]:
            if crawl["id"] != crawl_id:
                continue

            for i, component in enumerate(crawl["components"]):
                if component["component"] == execution.component:
                    crawl["components"][i] = execution_data

                    break
            else:
                crawl["components"].append(execution_data)

            crawl.update(fields)

            break

        await self._database["urls"].update_one({"hash": document["hash"]}, {"$set": {"crawls": document["crawls"]}})

    async def save_domain(self, domain: str) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        await self._database["domains"].update_one(
            {"domain": domain},
            {"$setOnInsert": asdict(DomainModel(domain=domain))},
            upsert=True,
        )

    async def get_distinct_domains(self, excluded: list[str], limit: int) -> list[str]:
        if self._client is None:
            raise RuntimeError("Service not started.")

        pipeline = [
            {"$match": {"domain": {"$nin": excluded}, "crawls": {"$size": 0}}},
            {
                "$group": {
                    "_id": "$domain",
                    "avgPriority": {"$avg": "$priority"}
                }
            },
            {"$sort": {"avgPriority": -1}},
            {"$limit": limit},
        ]

        cursor = await self._database["urls"].aggregate(pipeline)
        documents = await cursor.to_list(length=limit)

        return [document["_id"] for document in documents]

    async def get_domain_urls(self, domain: str, limit: int) -> list[URLModel]:
        if self._client is None:
            raise RuntimeError("Service not started.")

        cursor = self._database["urls"].find(
            {"domain": domain, "crawls": {"$size": 0}}).sort("priority", -1).limit(limit)
        documents = await cursor.to_list(length=limit)

        urls: list[URLModel] = []

        for document in documents:
            url = URLModel(
                address=document["address"],
                hash=document["hash"],
                domain=document["domain"],
                priority=document["priority"],
                correlation_id=document["correlation_id"],
                crawls=[Crawl.from_document(crawl) for crawl in document["crawls"]],
                discovered_at=document["discovered_at"],
            )

            urls.append(url)

        return urls

    async def get_excluded_domains(self) -> list[str]:
        if self._client is None:
            raise RuntimeError("Service not started.")

        now = datetime.now(timezone.utc)

        cursor = self._database["domains"].find(
            {"$or": [
                {"status": DomainStatus.BLOCKED.value},
                {"status": DomainStatus.LOCKED.value, "locked_until": {"$gt": now}},
            ]},
            {"domain": 1},
        )
        documents = await cursor.to_list(length=None)

        return [document["domain"] for document in documents]

    async def lock_domain(self, domain: str, until: datetime, reason: str) -> DomainStatus:
        if self._client is None:
            raise RuntimeError("Service not started.")

        status = DomainStatus.LOCKED

        result = await self._database["domains"].find_one_and_update(
            {"domain": domain},
            {
                "$inc": {"lock_count": 1},
                "$set": {"status": status.value, "locked_until": until, "last_locked_at": datetime.now(timezone.utc)},
            },
            upsert=True,
            return_document=True,
        )

        if result["lock_count"] >= MAX_DOMAIN_CONSECUTIVE_LOCKS:
            status = DomainStatus.BLOCKED

            await self._database["domains"].update_one(
                {"domain": domain},
                {"$set": {
                    "status": status.value,
                    "blocked_at": datetime.now(timezone.utc),
                    "blocked_reason": reason,
                    "locked_until": None,
                }},
            )

        return status

    async def unlock_domain(self, domain: str) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        await self._database["domains"].update_one(
            {"domain": domain, "lock_count": {"$gt": 0}},
            {"$set": {"status": DomainStatus.ACTIVE.value, "lock_count": 0, "locked_until": None}},
        )

    async def record_language(self, domain: str, language: str, allowed: bool,
                              threshold: int = 5) -> None:
        if self._client is None:
            raise RuntimeError("Service not started.")

        result = await self._database["domains"].find_one_and_update(
            {"domain": domain},
            {"$inc": {f"metrics.languages.{language}": 1}},
            upsert=True,
            return_document=True,
        )

        if allowed:
            return None

        count = result["metrics"]["languages"][language]

        if count < threshold:
            return None

        await self._database["domains"].update_one(
            {"domain": domain},
            {"$set": {
                "status": DomainStatus.BLOCKED.value,
                "blocked_at": datetime.now(timezone.utc),
                "blocked_reason": f"Found {count} pages for disallowed language ({language}).",
            }},
        )

        return None
