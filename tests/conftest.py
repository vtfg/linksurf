import pytest

from linksurf.common.settings import Settings
from linksurf.events.bus import EventBus
from linksurf.services import Services
from tests.fakes.listeners import FakeListener
from tests.fakes.services import FakeDatabase, FakeBlobStorage, FakeCache, FakeFetcher, FakeLock


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def listener():
    EventBus._instance = None

    listener = FakeListener()
    
    EventBus().on("*", listener.handle)

    try:
        yield listener
    finally:
        EventBus._instance = None


@pytest.fixture
async def services(settings):
    database = FakeDatabase()
    blob_storage = FakeBlobStorage()
    cache = FakeCache()
    fetcher = FakeFetcher()
    lock = FakeLock()

    services = Services(database, blob_storage, cache, fetcher, lock)

    await services.connect(settings)

    try:
        yield services
    finally:
        await services.disconnect()
