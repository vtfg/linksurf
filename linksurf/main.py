from linksurf import Linksurf
from linksurf.broker.base import Broker
from linksurf.common.fixture import COUNTRIES
from linksurf.common.models import URL
from linksurf.components.frontier.filters import (
    URLSeenFilter,
    CountryFilter,
    URLExtensionFilter,
    RobotsExclusionFilter,
)
from linksurf.components.frontier.middlewares import (
    DNSMiddleware,
    CountryMiddleware,
    RobotsExclusionMiddleware,
    URLNormalizationMiddleware
)
from linksurf.components.storage.filters import ContentSeenFilter
from linksurf.services import Services, Database, BlobStorage, Cache, Fetcher

if __name__ == "__main__":
    seed = [
        URL("http://example.com"),
        URL("https://example.com"),
        URL("ftp://username:password@example.com"),
    ]

    services = Services(
        database=Database(),
        blob_storage=BlobStorage(),
        cache=Cache(),
        fetcher=Fetcher(),
    )

    broker = Broker()

    linksurf = Linksurf(services, broker)

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
        DNSMiddleware(),
        CountryMiddleware(),
        RobotsExclusionMiddleware(),
        URLNormalizationMiddleware(),
    ]

    linksurf.frontier.filters = [
        URLSeenFilter(),
        CountryFilter(allowed=[COUNTRIES["BRA"]]),
        URLExtensionFilter(allowed=["html", "pdf"]),
        RobotsExclusionFilter(),
    ]

    linksurf.storage.filters = [
        ContentSeenFilter(),
    ]

    linksurf.run(seed)
