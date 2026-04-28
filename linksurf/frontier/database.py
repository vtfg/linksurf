from typing import Annotated

from beanie import Document, Indexed, init_beanie
from beanie.odm.operators.update.general import Set
from pymongo import AsyncMongoClient, IndexModel, ASCENDING

from linksurf.helpers import get_env
from linksurf.models import Link as LinkBase, LinkType, Metadata, MetaTag  # noqa: F401

MONGODB_URL = get_env("MONGODB_URL", default="mongodb://root:root@localhost:27017")


class Page(Document):
    url: Annotated[str, Indexed(unique=True)]
    url_hash: str
    html_url: str
    metadata: Metadata

    class Settings:
        name = "pages"


class Link(LinkBase, Document):
    class Settings:
        name = "links"
        indexes = [
            IndexModel([("source", ASCENDING), ("target", ASCENDING)], unique=True),
        ]


async def init_database() -> None:
    client = AsyncMongoClient(MONGODB_URL)

    await init_beanie(database=client.linksurf, document_models=[Page, Link])


async def save_page(url: str, url_hash: str, html_url: str, metadata: Metadata) -> None:
    await Page.find_one(Page.url == url).upsert(
        Set({Page.url_hash: url_hash, Page.html_url: html_url, Page.metadata: metadata}),
        on_insert=Page(url=url, url_hash=url_hash, html_url=html_url, metadata=metadata),
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
