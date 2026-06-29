from linksurf.application import Linksurf
from linksurf.broker.rabbitmq import RabbitMQBroker
from linksurf.common.models import URL
from linksurf.common.settings import Settings

from linksurf.services import Services
from linksurf.services.blob import S3BlobStorage
from linksurf.services.cache import RedisCache
from linksurf.services.database import MongoDatabase
from linksurf.services.fetcher import RequestsFetcher

if __name__ == "__main__":
    seed = [
        URL("http://example.com"),
        URL("https://example.com"),
        URL("https://example.com/abc"),
        URL("https://example.com/def"),
        URL("https://example.com/ghi"),
        URL("http://example.com:80"),
        URL("https://example.com:443"),
        URL("https://example.com:42069"),
        URL("ftp://username:password@example.com"),
        # URL("https://www.goodreads.com/"),
        # URL("https://www.reddit.com/"),
    ]

    services = Services(
        database=MongoDatabase(url="mongodb://root:root@localhost:27017"),
        blob_storage=S3BlobStorage(
            bucket="linksurf",
            endpoint_url="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
        ),
        cache=RedisCache(
            host="localhost",
            port=6379,
        ),
        fetcher=RequestsFetcher(),
    )

    broker = RabbitMQBroker()

    settings = Settings(
        identifier="Linksurf",
        user_agent="Linksurf/1.0",
    )

    linksurf = Linksurf(settings=settings, services=services, broker=broker)

    # Future implementation
    # Extensions contain a list of middlewares for the frontier and filters for both frontier and storage
    # They may also have lifecycle events and scheduled events (i.e. to check proxies periodically)
    # Extensions can also be HTTP servers, like an Admin Panel that shows metrics about the crawler
    linksurf.extensions = [
        # ProxyPoolExtension(proxies=list[URL?]) -> manages proxies and returns one before every request
    ]

    linksurf.run(seed)
