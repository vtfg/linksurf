from linksurf.common.models import HTTPRequest, HTTPRequestMetadata
from linksurf.services.fetcher import Fetcher


class IPInfoError(Exception):
    pass


class IPInfoClient:
    """
    Wrapper around IPinfo's Lite API (https://ipinfo.io) for GeoIP lookups.
    Unlimited on the free "Lite" tier for country-level data.

    Uses the plaintext `/country_code` endpoint rather than the full JSON response.
    Reuses the crawler's Fetcher so these calls are emitted.
    """

    def __init__(self, fetcher: Fetcher, token: str):
        self._fetcher = fetcher
        self._token = token

    async def lookup(self, ip: str, correlation_id: str, component: str) -> str | None:
        """
        Returns the ISO 3166-1 alpha-2 country code for an IP, or None if it can't be determined.

        Raises on request failure (network error or a non-2xx response).
        """

        request = HTTPRequest(
            url=f"https://api.ipinfo.io/lite/{ip}/country_code?token={self._token}",
            metadata=HTTPRequestMetadata(correlation_id=correlation_id, component=component),
        )

        response = await self._fetcher.http(request)

        if not response.ok:
            raise IPInfoError(f"IPinfo returned status {response.status_code}.")

        code = response.text.strip()

        return code or None
