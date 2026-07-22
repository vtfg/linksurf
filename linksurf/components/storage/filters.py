from linksurf.components.base import Filter, FilterResponse


# Ignores the URL if content is duplicate
class ContentSeenFilter(Filter):
    async def execute(self, metadata) -> FilterResponse:
        raise NotImplementedError()
