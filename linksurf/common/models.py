from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit


class URL:
    def __init__(self, address: str):
        self.address = address

        split = urlsplit(address)

        self.scheme = split.scheme
        self.netloc = split.netloc
        self.path = split.path
        self.query = split.query
        self.fragment = split.fragment


class LinkType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


@dataclass
class Link:
    source: str
    target: str
    type: LinkType
    text: str
    rel: str


class HTTPRequest:
    pass


class HTTPResponse:
    pass


class Content:
    def __init__(self):
        self.raw = None
        self.type = None


class Country:
    """
    Basic data class of ISO 3166-1's elements.
    """

    def __init__(self, alpha_2_code: str, alpha_3_code: str, numeric_code: str):
        self.alpha_2_code = alpha_2_code
        self.alpha_3_code = alpha_3_code
        self.numeric_code = numeric_code
