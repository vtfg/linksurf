from dotenv import load_dotenv

from linksurf.application import Linksurf, Seed
from linksurf.broker.rabbitmq import RabbitMQBroker
from linksurf.common.settings import Settings
from linksurf.services import Services
from linksurf.services.blob import S3BlobStorage
from linksurf.services.cache import RedisCache
from linksurf.services.database import MongoDatabase
from linksurf.services.fetcher import RequestsFetcher
from linksurf.utils.env import get_env

load_dotenv()

if __name__ == "__main__":
    seed = Seed.from_file("seed.txt")

    services = Services(
        database=MongoDatabase(url=get_env("MONGODB_URL")),
        blob_storage=S3BlobStorage(
            bucket=get_env("S3_BUCKET"),
            endpoint_url=get_env("S3_ENDPOINT_URL"),
            access_key=get_env("S3_ACCESS_KEY"),
            secret_key=get_env("S3_SECRET_KEY"),
        ),
        cache=RedisCache(
            host=get_env("REDIS_HOST"),
            port=get_env("REDIS_PORT", cast=int),
        ),
        fetcher=RequestsFetcher(),
    )

    broker = RabbitMQBroker()

    settings = Settings(
        identifier="Linksurf",
        user_agent="Linksurf/1.0",
        proxy=get_env("PROXY_URL", required=False),
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
