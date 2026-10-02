from linksurf.common.settings import Settings
from linksurf.services import Database, BlobStorage, Cache, Fetcher, Lock


class FakeDatabase(Database):
    async def on_start(self, settings):
        pass

    async def on_stop(self):
        pass


class FakeBlobStorage(BlobStorage):
    async def on_start(self, settings):
        pass

    async def on_stop(self):
        pass


class FakeCache(Cache):
    async def on_start(self, settings):
        pass

    async def on_stop(self):
        pass


class FakeFetcher(Fetcher):
    async def on_start(self, settings):
        pass

    async def on_stop(self):
        pass


class FakeLock(Lock):
    async def on_start(self, settings: Settings):
        pass

    async def on_stop(self):
        pass
