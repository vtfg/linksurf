import os
from urllib.parse import urlsplit


def get_env(name, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    else:
        raise KeyError("Missing env variable:", name)


def get_base_domain(url: str):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
