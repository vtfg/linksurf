from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from linksurf.common.settings import Settings
from linksurf.services.base import Service


class Database(Service):
    NAME = "database"

    # Returns the saved row's ID
    async def save_url(self, data: dict) -> str:
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

    async def save_url(self, data: dict) -> str:
        if self._client is None or self._database is None:
            raise RuntimeError("Service not started.")

        result = await self._database["urls"].find_one_and_update(
            {"hash": data["hash"]},
            {"$set": data},
            {"_id": True},
            upsert=True,
            return_document=True,
        )

        return result["_id"]
