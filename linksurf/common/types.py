class Error:
    retriable: bool

    def __init__(self, message: str, retriable: bool = True):
        self.message = message
        self.retriable = retriable


class Response[T]:
    def __init__(self, data: T | None, error: Error | None):
        self.data = data
        self.error = error
