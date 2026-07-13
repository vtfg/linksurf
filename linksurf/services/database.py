from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from linksurf.common.models import Redirect, Content, HTTPRequestSummary, HTTPResponseSummary
from linksurf.common.payload import Status
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


class Database(Service):
    NAME = "database"

    # Returns the saved row's ID
    async def save_url(self, data: URLModel) -> str:
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
            {"hash": data.hash},
            {"$set": asdict(data)},
            {"_id": True},
            upsert=True,
            return_document=True,
        )

        return result["_id"]
