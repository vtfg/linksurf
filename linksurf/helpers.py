import hashlib
import json
import os
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID

import tldextract

# Disables suffix list request
_tldextract = tldextract.TLDExtract(suffix_list_urls=())


def get_env(name, cast=str, default: str | int = None):
    if name in os.environ:
        return cast(os.environ[name])
    elif default is not None:
        return cast(default)
    else:
        raise KeyError("Missing env variable:", name)


def get_base_domain(url: str):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def get_domain_name(url: str):
    parts = urlsplit(url)
    return parts.netloc


def get_root_domain(url: str) -> str:
    extracted = _tldextract(url)

    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"

    return extracted.domain


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def strip(value: str | None) -> str | None:
    return value.strip() if value else None


class ObjectEncoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, UUID):
            return str(object)
        if isinstance(object, Enum):
            return object.name
        return super().default(object)
