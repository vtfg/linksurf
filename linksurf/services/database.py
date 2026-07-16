from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from linksurf.common.models import Redirect, Content, HTTPRequestSummary, HTTPResponseSummary
from linksurf.common.payload import Status, Payload
from linksurf.common.settings import Settings
from linksurf.services.base import Service


@dataclass
class URLModel:
    address: str
    hash: str
    domain: str
    priority: int
    correlation_id: str
    status: Status = Status.PENDING
    request: HTTPRequestSummary | None = None
    response: HTTPResponseSummary | None = None
    content: Content | None = None
    redirects: list[Redirect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = datetime.now(timezone.utc)
    fetched_at: datetime | None = None

    @classmethod
    def from_payload(cls, payload: Payload, status: Status = Status.PENDING) -> URLModel:
        return cls(
            address=payload.url.address,
            hash=payload.url.hash,
            domain=payload.url.domain,
            priority=payload.priority,
            status=status,
            correlation_id=payload.correlation_id,
            request=payload.request,
            response=payload.response,
            content=payload.content,
            redirects=payload.redirects,
            metadata={k: v for k, v in payload.metadata.items() if k != "links"},
            discovered_at=payload.discovered_at,
            fetched_at=payload.fetched_at,
        )


class Database(Service):
    NAME = "database"

    async def save_url(self, data: URLModel) -> str:
        """
        Save a URL to the database and return its ID.
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
        Gets a list of N (`limit`) URLs for a domain after ordering by priority.
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

    async def save_url(self, data: URLModel) -> str:
        if self._client is None or self._database is None:
            raise RuntimeError("Service not started.")

        result = await self._database["urls"].find_one_and_update(
            {"correlation_id": data.correlation_id},
            {"$set": asdict(data)},
            {"_id": True},
            upsert=True,
            return_document=True,
        )

        return result["_id"]

    async def get_distinct_domains(self, excluded: list[str], limit: int) -> list[str]:
        if self._client is None:
            raise RuntimeError("Service not started.")

        pipeline = [
            {"$match": {"domain": {"$nin": excluded}, "status": Status.PENDING.value}},
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
            {"domain": domain, "status": Status.PENDING.value}).sort("priority", -1).limit(limit)
        documents = await cursor.to_list(length=limit)

        urls: list[URLModel] = []

        for document in documents:
            url = URLModel(
                address=document["address"],
                hash=document["hash"],
                domain=document["domain"],
                priority=document["priority"],
                status=Status(document["status"]),
                correlation_id=document["correlation_id"],
                request=HTTPRequestSummary(**document["request"]) if document["request"] else None,
                response=HTTPResponseSummary(**document["response"]) if document["response"] else None,
                content=Content(**document["content"]) if document["content"] else None,
                redirects=[Redirect(**redirect) for redirect in document["redirects"]] if document["redirects"] else [],
                metadata=document["metadata"],
                discovered_at=document["discovered_at"],
                fetched_at=document["fetched_at"],
            )

            urls.append(url)

        return urls
