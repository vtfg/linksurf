from linksurf.common.settings import Settings
from linksurf.logger import Logger
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

    async def connect(self, settings: Settings) -> None:
        services = [self.database, self.blob_storage, self.cache, self.fetcher]

        for service in services:
            service_name = type(service).__name__

            try:
                await service.on_start(settings)
            except Exception:
                Logger().exception("service.error", service=service_name, error="Service startup failed.")

                raise

            Logger().info("service.start", service=service_name)

    async def disconnect(self) -> None:
        services = [self.database, self.blob_storage, self.cache, self.fetcher]

        for service in services:
            service_name = type(service).__name__

            try:
                await service.on_stop()
            except Exception:
                Logger().exception("service.error", service=service_name, error="Service shutdown failed.")

                raise

            Logger().info("service.stop", service=service_name)
