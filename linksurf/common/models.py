from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit, urlunsplit

from linksurf.utils.url import hash_url


class URL:
    def __init__(self, address: str):
        split = urlsplit(address)

        self.scheme = split.scheme
        self.domain = split.netloc
        self.path = split.path
        self.query = split.query
        self.fragment = split.fragment

    @property
    def address(self):
        return urlunsplit((self.scheme, self.domain, self.path, self.query, self.fragment))

    @property
    def hash(self):
        return hash_url(self.address)

    @property
    def origin(self):
        """ Returns a string of {scheme}://{domain} """

        return f"{self.scheme}://{self.domain}"


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

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


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

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

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


@dataclass
class Content:
    key: str
    type: str


class Country:
    """
    Basic data class of ISO 3166-1's elements.
    """

    def __init__(self, alpha_2_code: str, alpha_3_code: str, numeric_code: str):
        self.alpha_2_code = alpha_2_code
        self.alpha_3_code = alpha_3_code
        self.numeric_code = numeric_code
