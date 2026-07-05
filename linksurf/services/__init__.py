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

    def connect(self, settings: Settings) -> None:
        for value in vars(self).values():
            if not isinstance(value, Service):
                continue

            service_name = type(value).__name__

            try:
                value.on_start(settings)
            except Exception:
                Logger().exception("service.error", service=service_name, error="Service startup failed.")

                raise

            Logger().info("service.start", service=service_name)

    def disconnect(self) -> None:
        for value in vars(self).values():
            if not isinstance(value, Service):
                continue

            service_name = type(value).__name__

            try:
                value.on_stop()
            except Exception:
                Logger().exception("service.error", service=service_name, error="Service shutdown failed.")

                raise

            Logger().info("service.stop", service=service_name)
