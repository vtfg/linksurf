from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from linksurf.common.types import CaseInsensitiveDict
from linksurf.utils.url import hash_url, normalize_url


class URL:
    def __init__(self, address: str):
        split = urlsplit(normalize_url(address))

        self.scheme = split.scheme
        self.domain = split.hostname  # domain only
        self._netloc = split.netloc  # domain:port
        self.path = split.path
        self.query = split.query
        self.fragment = split.fragment

        if split.port:
            self.port = split.port
        else:
            self.port = 80 if split.scheme == "http" else 443

    @property
    def address(self):
        return urlunsplit((self.scheme, self._netloc, self.path, self.query, self.fragment))

    @property
    def hash(self):
        return hash_url(self.address)

    @property
    def origin(self):
        """ Returns a string of {scheme}://{domain} """

        return f"{self.scheme}://{self.domain}"

    @property
    def extension(self) -> str | None:
        segment = self.path.rsplit("/", 1)[-1]

        if "." in segment:
            return segment.rsplit(".", 1)[-1].lower() or None

        return None

    @property
    def path_depth(self) -> int:
        return len([s for s in self.path.split("/") if s])


class LinkType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


@dataclass
class Link:
    source: str
    target: str
    raw_target: str
    type: LinkType
    text: str | None
    rel: str | None


@dataclass(frozen=True)
class HTTPRequestSummary:
    url: str
    method: str = "GET"
    user_agent: str | None = None
    proxy: str | None = None
    timeout: float = 30.0
    follow_redirects: bool = False


@dataclass
class HTTPRequestMetadata:
    correlation_id: str
    component: str


@dataclass()
class HTTPRequest:
    url: str
    method: str = "GET"
    user_agent: str | None = None
    proxy: str | None = None
    timeout: float = 30.0
    follow_redirects: bool = False
    metadata: HTTPRequestMetadata = field(default_factory=HTTPRequestMetadata)

    def to_summary(self) -> HTTPRequestSummary:
        return HTTPRequestSummary(
            url=self.url,
            method=self.method,
            user_agent=self.user_agent,
            proxy=self.proxy,
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
        )


@dataclass
class Redirect:
    source: str
    target: str
    status_code: int
    depth: int


@dataclass(frozen=True)
class HTTPResponseSummary:
    status_code: int
    headers: dict[str, str]
    encoding: str | None
    elapsed_ms: float
    size_bytes: int
    redirects: list[Redirect]

    def __post_init__(self):
        object.__setattr__(self, "headers", CaseInsensitiveDict(self.headers))

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")


@dataclass(frozen=True)
class HTTPResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    encoding: str | None
    elapsed_ms: float
    redirects: list[Redirect]
    request: HTTPRequest

    def __post_init__(self):
        object.__setattr__(self, "headers", CaseInsensitiveDict(self.headers))

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    @property
    def content_length(self) -> str | None:
        return self.headers.get("content-length")

    @property
    def text(self) -> str:
        return self.body.decode(self.encoding or "utf-8", errors="replace")

    def to_summary(self) -> HTTPResponseSummary:
        return HTTPResponseSummary(
            status_code=self.status_code,
            headers=self.headers,
            encoding=self.encoding,
            elapsed_ms=self.elapsed_ms,
            size_bytes=len(self.body),
            redirects=self.redirects,
        )


class MimeType(str, Enum):
    TEXT = "text/plain"
    HTML = "text/html"
    PDF = "application/pdf"
    UNKNOWN = "unknown"


@dataclass
class Content:
    key: str
    type: MimeType
    extracted: dict[str, dict[str, Any] | list[Any]] | None = None


class Country(str, Enum):
    """
    ISO 3166-1 alpha-2 country codes.
    """

    BRAZIL = "BR"
    USA = "US"


class Language(str, Enum):
    """
    ISO 639-1 language codes.
    """

    PORTUGUESE = "pt"
    ENGLISH = "en"


@dataclass
class ComponentExecution:
    component: str
    rules: list[str]
    deduplicator: str | None
    middlewares: list[str]
    filters: list[str]
    retries: int = 0
    # seen: bool | None -> future: response from Deduplicator (?!)
    error: str | None = None
    exception: str | None = None  # exception path
    retriable: bool | None = None
    started_at: datetime | None = None  # doesn't reset on retries
    finished_at: datetime | None = None


class CrawlStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ERRORED = "errored"
    FINISHED = "finished"


@dataclass
class Crawl:
    id: str = field(default_factory=lambda: uuid4().hex)
    components: list[ComponentExecution] = field(default_factory=list)
    status: CrawlStatus = CrawlStatus.PENDING
    request: HTTPRequestSummary | None = None
    response: HTTPResponseSummary | None = None
    content: Content | None = None
    redirects: list[Redirect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # first component's started_at
    finished_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # last component's finished_at

    @classmethod
    def from_document(cls, data: dict[str, Any]) -> Crawl:
        response = data.get("response")

        return cls(
            id=data["id"],
            components=[ComponentExecution(**component) for component in data["components"]],
            status=CrawlStatus(data.get("status", CrawlStatus.PENDING.value)),
            request=HTTPRequestSummary(**data["request"]) if data.get("request") else None,
            response=HTTPResponseSummary(
                **{**response, "redirects": [Redirect(**r) for r in response.get("redirects", [])]}
            ) if response else None,
            content=Content(**data["content"]) if data.get("content") else None,
            redirects=[Redirect(**r) for r in data.get("redirects", [])],
            metadata=data.get("metadata", {}),
            started_at=data["started_at"],
            finished_at=data["finished_at"],
        )
