from enum import Enum

from pydantic import BaseModel


class LinkType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


class Link(BaseModel):
    source: str
    target: str
    type: LinkType
    text: str | None = None
    nofollow: bool = False


class MetaTag(BaseModel):
    name: str
    content: str


class Metadata(BaseModel):
    title: str | None = None
    description: str | None = None
    lang: str | None = None
    tags: list[MetaTag] = []


class ReserveSlotBody(BaseModel):
    url: str


class ReserveSlotResponse(BaseModel):
    delay_ms: int


class PresignedUploadURLBody(BaseModel):
    url: str


class PresignedUploadURLResponse(BaseModel):
    presigned_url: str
    key: str


class SeedBody(BaseModel):
    url: str


class SubmitResultBody(BaseModel):
    url: str
    depth: int
    html_key: str
    metadata: Metadata
    links: list[Link]
