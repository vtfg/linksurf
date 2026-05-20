from typing import Any

from linksurf.common.fixture import COUNTRIES
from linksurf.components.base import Middleware, MiddlewareResponse


class DNSMiddleware(Middleware):
    """
    Queries the website's DNS and checks availability, IP, etc.
    """

    def execute(self, metadata: dict[str, Any]) -> MiddlewareResponse:
        pass


class CountryMiddleware(Middleware):
    """
    Computes the website's guessed country.
    """

    def execute(self, metadata) -> MiddlewareResponse:
        _ = metadata.get("domain")
        _ = metadata.get("ip")

        # Check domain TLD, fetch server IP location, etc.

        return MiddlewareResponse({"country": COUNTRIES["BRA"]}, None)


class RobotsExclusionMiddleware(Middleware):
    def execute(self, metadata) -> MiddlewareResponse:
        _ = metadata.get("domain")

        # Fetches robots.txt for domain, checks cache first

        return MiddlewareResponse({"robots": "..."}, None)


class URLNormalizationMiddleware(Middleware):
    def execute(self, metadata) -> MiddlewareResponse:
        url = metadata.get("url")

        # Normalizes the URL based on several factors (excludes UTMs, sorts query parameters, etc.)

        return MiddlewareResponse({"url": url}, None)
