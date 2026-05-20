from linksurf.common.models import Country
from linksurf.components.base import Filter, FilterResponse
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, CountryMiddleware


class URLSeenFilter(Filter):
    def execute(self, metadata) -> FilterResponse:
        pass


class CountryFilter(Filter):
    # There should be a way to validate if Middleware was executed before validating its data
    DEPENDS_ON = [CountryMiddleware]

    def __init__(self, allowed: list[Country]):
        self.allowed = allowed

    def execute(self, metadata) -> FilterResponse:
        country = metadata.get("country")

        if country not in self.allowed:
            return FilterResponse(False, None)

        return FilterResponse(True, None)


class URLExtensionFilter(Filter):
    def __init__(self, allowed: list[str]):
        self.allowed = allowed

    def execute(self, metadata) -> FilterResponse:
        extension = metadata.get("extension")

        if extension not in self.allowed:
            return FilterResponse(False, None)

        return FilterResponse(True, None)


class RobotsExclusionFilter(Filter):
    DEPENDS_ON = [RobotsExclusionMiddleware]

    def execute(self, metadata) -> FilterResponse:
        _ = metadata.get("robots")

        # Fetch robots.txt and checks if URL is excluded

        return FilterResponse(True, None)
