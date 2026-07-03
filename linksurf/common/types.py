class Error:
    def __init__(self,
                 message: str,
                 retriable: bool = True,
                 unexpected: bool = False,
                 exception: BaseException | None = None,
                 delay_seconds: int | None = None):
        self.message = message
        self.retriable = retriable
        self.unexpected = unexpected
        self.exception = exception
        self.delay_seconds = delay_seconds


class Response[T]:
    def __init__(self, data: T | None, error: Error | None):
        self.data = data
        self.error = error


class CaseInsensitiveDict(dict):
    """
    A dict subclass that normalizes all keys to lowercase.
    HTTP headers are case-insensitive per RFC 7230 — this enforces that at
    the storage level so lookups always work regardless of the casing used by
    the server or the caller.
    """

    def __init__(self, data=None, **kwargs):
        super().__init__()
        if data is not None:
            items = data.items() if hasattr(data, "items") else data
            for k, v in items:
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def __setitem__(self, key: str, value: str):
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key: str):
        return super().__getitem__(key.lower())

    def __contains__(self, key: object):
        return super().__contains__(key.lower() if isinstance(key, str) else key)

    def get(self, key: str, default=None):
        return super().get(key.lower(), default)
