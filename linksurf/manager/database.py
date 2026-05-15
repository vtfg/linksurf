from datetime import datetime
from typing import Annotated

from beanie import Document, Indexed, init_beanie
from beanie.odm.operators.update.general import Set
from pymongo import AsyncMongoClient

from linksurf.helpers import get_env
from linksurf.models import HttpInfo, Link as LinkBase, Page

MONGODB_URL = get_env("MONGODB_URL", default="mongodb://root:root@localhost:27017")


class Domain(Document):
    name: str
    last_crawled_at: datetime

    class Settings:
        name = "domains"


class URL(Document):
    address: Annotated[str, Indexed(unique=True)]
    hash: str
    http: HttpInfo
    headers: dict[str, str]
    type: str
    content_url: str
    page: Page
    first_crawled_at: datetime
    last_crawled_at: datetime

    class Settings:
        name = "urls"


class Link(LinkBase, Document):
    class Settings:
        name = "links"


async def init_database() -> None:
    client = AsyncMongoClient(MONGODB_URL)

    await init_beanie(database=client.linksurf, document_models=[Domain, URL, Link])


async def save_domain(name: str, last_crawled_at: datetime) -> None:
    await Domain.find_one(Domain.name == name).upsert(
        Set({
            Domain.last_crawled_at: last_crawled_at
        }),
        on_insert=Domain(
            name=name,
            last_crawled_at=last_crawled_at,
        ),
    )


async def save_url(
        address: str,
        url_hash: str,
        content_url: str,
        http: HttpInfo,
        headers: dict[str, str],
        type: str,
        page: Page,
        last_crawled_at: datetime,
) -> None:
    await URL.find_one(URL.address == address).upsert(
        Set({
            URL.hash: url_hash,
            URL.http: http,
            URL.headers: headers,
            URL.type: type,
            URL.content_url: content_url,
            URL.page: page,
            URL.last_crawled_at: last_crawled_at,
        }),
        on_insert=URL(
            address=address,
            hash=url_hash,
            http=http,
            headers=headers,
            type=type,
            content_url=content_url,
            page=page,
            first_crawled_at=last_crawled_at,
            last_crawled_at=last_crawled_at,
        ),
    )


async def save_links(links: list[Link]) -> None:
    for link in links:
        await Link.find_one(
            Link.source == link.source,
            Link.target == link.target,
        ).upsert(
            Set({Link.type: link.type, Link.text: link.text, Link.nofollow: link.nofollow}),
            on_insert=link,
        )
