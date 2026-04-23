from enum import Enum
from typing import Annotated

from beanie import Document, Indexed, init_beanie
from beanie.odm.operators.update.general import Set
from pydantic import BaseModel
from pymongo import AsyncMongoClient, IndexModel, ASCENDING

from linksurf.helpers import get_env, get_base_domain


class URL:
    def __init__(self, address: str, depth: int = 0):
        self.address = address
        self.domain = get_base_domain(address)
        self.depth = depth


class LinkType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class MetaTag(BaseModel):
    name: str
    content: str


class Metadata(BaseModel):
    title: str | None = None
    description: str | None = None
    lang: str | None = None
    tags: list[MetaTag] = []


class Page(Document):
    url: Annotated[str, Indexed(unique=True)]
    url_hash: str
    html_url: str
    metadata: Metadata

    class Settings:
        name = "pages"


class Link(Document):
    source: str
    target: str
    type: LinkType
    text: str | None = None
    nofollow: bool = False

    class Settings:
        name = "links"
        indexes = [
            IndexModel([("source", ASCENDING), ("target", ASCENDING)], unique=True),
        ]


async def init_database():
    mongodb_url = get_env("MONGODB_URL", default="mongodb://root:root@localhost:27017")
    client = AsyncMongoClient(mongodb_url)
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
