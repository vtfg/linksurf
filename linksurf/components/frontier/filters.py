from linksurf.common.models import Country
from linksurf.common.payload import Payload
from linksurf.components.base import Filter, FilterResponse
from linksurf.components.frontier.middlewares import RobotsExclusionMiddleware, CountryMiddleware


class URLSeenFilter(Filter):
    def execute(self, payload: Payload) -> FilterResponse:
        pass


class CountryFilter(Filter):
    DEPENDS_ON = [CountryMiddleware]

    def __init__(self, allowed: list[Country]):
        self.allowed = allowed

    def execute(self, payload: Payload) -> FilterResponse:
        country = payload.get_metadata("country")

        if country not in self.allowed:
            return FilterResponse(False, None)

        return FilterResponse(True, None)


class URLExtensionFilter(Filter):
    def __init__(self, allowed: list[str]):
        self.allowed = allowed

    def execute(self, payload: Payload) -> FilterResponse:
        extension = payload.get_metadata("extension")

        if extension not in self.allowed:
            return FilterResponse(False, None)

        return FilterResponse(True, None)


class RobotsExclusionFilter(Filter):
    DEPENDS_ON = [RobotsExclusionMiddleware]

    def execute(self, payload: Payload) -> FilterResponse:
        # Fetch robots.txt and checks if URL is excluded

        return FilterResponse(True, None)
