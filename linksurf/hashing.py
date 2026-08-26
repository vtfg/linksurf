import mmh3

BUCKET_COUNT = 64


def bucketize(domain: str) -> int:
    """
    Maps a domain to its bucket (1 to BUCKET_COUNT) so the work can be distributed between instances (workers).
    """

    return mmh3.hash(domain, signed=False) % BUCKET_COUNT + 1
