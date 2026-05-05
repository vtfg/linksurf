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


class Page(BaseModel):
    title: str | None = None
    description: str | None = None
    lang: str | None = None
    metadata: list[MetaTag] = []


class HttpInfo(BaseModel):
    status_code: int
    size: int
    response_time: int


class ReserveSlotBody(BaseModel):
    url: str


class ReserveSlotResponse(BaseModel):
    delay_ms: int
    proxy: str


class PresignedUploadURLBody(BaseModel):
    url: str


class PresignedUploadURLResponse(BaseModel):
    presigned_url: str
    key: str


class SeedBody(BaseModel):
    url: str


class SeedResponse(BaseModel):
    ok: bool


class SubmitResultBody(BaseModel):
    address: str
    depth: int
    content_key: str
    http: HttpInfo
    headers: dict[str, str]
    type: str
    page: Page
    links: list[Link]
