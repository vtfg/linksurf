from linksurf.application import Linksurf
from linksurf.broker.rabbitmq import RabbitMQBroker
from linksurf.common.models import URL
from linksurf.components.frontier.filters import URLSeenFilter, RobotsExclusionFilter
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, URLNormalizationMiddleware, \
    DNSMiddleware
from linksurf.services import Services
from linksurf.services.blob import S3BlobStorage
from linksurf.services.cache import RedisCache
from linksurf.services.database import MongoDatabase
from linksurf.services.fetcher import RequestsFetcher

if __name__ == "__main__":
    seed = [
        URL("http://example.com"),
        URL("https://example.com"),
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

    linksurf = Linksurf(services=services, broker=broker)

    # linksurf.config = Config(
    #     user_agent="..."
    # )

    # Future implementation
    # Extensions contain a list of middlewares for the frontier and filters for both frontier and storage
    # They may also have lifecycle events and scheduled events (i.e. to check proxies periodically)
    # Extensions can also be HTTP servers, like an Admin Panel that shows metrics about the crawler
    linksurf.extensions = [
        # ProxyPoolExtension(proxies=list[URL?]) -> manages proxies and returns one before every request
    ]

    linksurf.frontier.middlewares = [
        URLNormalizationMiddleware(),
        DNSMiddleware(),
        # CountryMiddleware(),
        RobotsExclusionMiddleware(),
    ]

    linksurf.frontier.filters = [
        URLSeenFilter(),
        # CountryFilter(allowed=[COUNTRIES["BRA"]]),
        # URLExtensionFilter(allowed=["html", "pdf"]), #? [Maybe this should be a Downloader middleware+filter that sends a HEAD request]
        RobotsExclusionFilter(),
    ]

    linksurf.downloader.middlewares = [
        # ContentTypeMiddleware()
    ]

    linksurf.downloader.filters = [
        # ContentTypeFilter(allowed=[MimeTypes.HTML, MimeTypes.PDF]),
    ]

    linksurf.storage.filters = [
        # ContentSeenFilter(),
    ]

    linksurf.run(seed)
