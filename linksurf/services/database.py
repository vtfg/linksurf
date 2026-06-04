import logging

from pymongo import MongoClient
from pymongo.database import Database as MongoDb

from linksurf.services.base import Service

logger = logging.getLogger(__name__)


class Database(Service):
    NAME = "database"

    # Returns the saved row's ID
    def save_url(self, data: dict) -> str:
        pass


class MongoDatabase(Database):
    def __init__(self, url: str, name: str = "linksurf"):
        self.uri = url
        self.name = name
        self._client: MongoClient | None = None
        self._database: MongoDb | None = None

    def on_start(self):
        self._client = MongoClient(self.uri)
        self._database = self._client[self.name]

        print(f"Connected to MongoDB at {self.uri} (db: {self.name})")

    def on_stop(self):
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None

    def save_url(self, data: dict) -> str:
        result = self._database["urls"].find_one_and_update(
            {"hash": data["hash"]},
            {"$set": data},
            {"_id": True},
            upsert=True,
            return_document=True,
        )

        return result["_id"]
