from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit, urlunsplit

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
    type: LinkType
    text: str | None
    rel: str | None


@dataclass(frozen=True)
class HTTPRequestSummary:
    method: str = "GET"
    proxy: str | None = None
    timeout: float = 30.0
    follow_redirects: bool = False


@dataclass(frozen=True)
class HTTPRequest:
    url: str
    method: str = "GET"
    proxy: str | None = None
    timeout: float = 30.0
    follow_redirects: bool = False

    def to_summary(self) -> HTTPRequestSummary:
        return HTTPRequestSummary(
            method=self.method,
            proxy=self.proxy,
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
        )


@dataclass(frozen=True)
class HTTPResponseSummary:
    status_code: int
    headers: dict[str, str]
    encoding: str
    elapsed_ms: float
    redirects: list[str]

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
    encoding: str
    elapsed_ms: float
    redirects: list[str]
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
    def text(self) -> str:
        return self.body.decode(self.encoding or "utf-8", errors="replace")

    def to_summary(self) -> HTTPResponseSummary:
        return HTTPResponseSummary(
            status_code=self.status_code,
            headers=self.headers,
            encoding=self.encoding,
            elapsed_ms=self.elapsed_ms,
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


class Country:
    """
    Basic data class of ISO 3166-1's elements.
    """

    def __init__(self, alpha_2_code: str, alpha_3_code: str, numeric_code: str):
        self.alpha_2_code = alpha_2_code
        self.alpha_3_code = alpha_3_code
        self.numeric_code = numeric_code
