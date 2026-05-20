from linksurf.services.base import Service
from linksurf.services.blob import BlobStorage
from linksurf.services.cache import Cache
from linksurf.services.database import Database
from linksurf.services.fetcher import Fetcher


class Services:
    def __init__(self, database: Database, blob_storage: BlobStorage, cache: Cache, fetcher: Fetcher):
        self.database = database
        self.blob_storage = blob_storage
        self.cache = cache
        self.fetcher = fetcher

    def connect(self):
        for value in vars(self).values():
            if isinstance(value, Service):
                value.on_start()

    def disconnect(self):
        for value in vars(self).values():
            if isinstance(value, Service):
                value.on_stop()
