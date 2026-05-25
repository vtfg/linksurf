from linksurf.common.fixture import COUNTRIES
from linksurf.common.payload import Payload
from linksurf.components.base import Middleware, MiddlewareResponse


class DNSMiddleware(Middleware):
    """
    Queries the website's DNS and checks availability, IP, etc.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        pass


class CountryMiddleware(Middleware):
    """
    Computes the website's guessed country.
    """

    def execute(self, payload: Payload) -> MiddlewareResponse:
        _ = payload.url.domain
        _ = payload.get_metadata("ip")

        # Check domain TLD, fetch server IP location, etc.

        payload.add_metadata("country", COUNTRIES["bra"])

        return MiddlewareResponse(payload, None)


class RobotsExclusionMiddleware(Middleware):
    def execute(self, payload: Payload) -> MiddlewareResponse:
        _ = payload.url.domain

        # Fetches robots.txt for domain, checks cache first

        payload.add_metadata({"robots": "..."})

        return MiddlewareResponse(payload, None)


class URLNormalizationMiddleware(Middleware):
    def execute(self, payload: Payload) -> MiddlewareResponse:
        url = payload.url.domain

        # Normalizes the URL based on several factors (excludes UTMs, sorts query parameters, etc.)

        return MiddlewareResponse(payload, None)
