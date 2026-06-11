from linksurf.application import Linksurf
from linksurf.broker.rabbitmq import RabbitMQBroker
from linksurf.common.constants import TEN_MEGABYTES_IN_BYTES
from linksurf.common.models import URL, MimeType
from linksurf.common.settings import Settings
from linksurf.components.downloader.filters import ContentTypeFilter, ContentLengthFilter
from linksurf.components.downloader.middlewares import (
    ContentTypeMiddleware,
    RateLimiterMiddleware,
    ContentLengthMiddleware,
)
from linksurf.components.frontier.filters import RobotsExclusionFilter
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, DNSMiddleware
from linksurf.components.frontier.rules import (
    SchemeRule,
    URLExtensionRule,
    URLLimitsRule,
    BlockedDomainsRule,
    BLOCKED_EXTENSIONS,
)
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

    linksurf = Linksurf(services=services, broker=broker, settings=settings)

    # Future implementation
    # Extensions contain a list of middlewares for the frontier and filters for both frontier and storage
    # They may also have lifecycle events and scheduled events (i.e. to check proxies periodically)
    # Extensions can also be HTTP servers, like an Admin Panel that shows metrics about the crawler
    linksurf.extensions = [
        # ProxyPoolExtension(proxies=list[URL?]) -> manages proxies and returns one before every request
    ]

    linksurf.frontier.rules = [
        SchemeRule(allowed=["http", "https"]),
        URLExtensionRule(blocked=BLOCKED_EXTENSIONS),
        URLLimitsRule(max_length=2048, max_path_depth=10),
        BlockedDomainsRule(blocked=["google.com"]),
    ]

    linksurf.frontier.middlewares = [
        DNSMiddleware(),
        # CountryMiddleware(),
        RobotsExclusionMiddleware(),
    ]

    linksurf.frontier.filters = [
        # CountryFilter(allowed=[COUNTRIES["BRA"]]),
        RobotsExclusionFilter(),
    ]

    linksurf.downloader.middlewares = [
        ContentTypeMiddleware(),
        ContentLengthMiddleware(),
        RateLimiterMiddleware(),
    ]

    linksurf.downloader.filters = [
        ContentTypeFilter(allowed=[MimeType.HTML]),
        ContentLengthFilter(max_bytes=TEN_MEGABYTES_IN_BYTES),
    ]

    linksurf.storage.filters = [
        # ContentSeenFilter(),
    ]

    linksurf.run(seed)
