import json
import os
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID


def get_env(name, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    else:
        raise KeyError("Missing env variable:", name)


def get_base_domain(url: str):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"

class ObjectEncoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, UUID):
            return str(object)
        if isinstance(object, Enum):
            return object.name
        return super().default(object)
