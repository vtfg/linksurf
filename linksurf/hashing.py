import mmh3

from linksurf.common.models import URL

BUCKET_COUNT = 64


def bucketize(url: URL) -> int:
    return mmh3.hash(url.domain) % BUCKET_COUNT
