import httpx

from linksurf.manager.cache import get_geoip_cache, get_next_proxy, set_geoip_cache

_IP_API_URL = "http://ip-api.com/json/{host}?fields=countryCode"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client

    if _client is None:
        _client = httpx.AsyncClient(timeout=5.0)
        
    return _client


async def is_brazilian_ip(hostname: str) -> bool:
    cached = await get_geoip_cache(hostname)

    if cached is not None:
        return cached == "BR"

    try:
        proxy = await get_next_proxy()
        response = await _get_client().get(_IP_API_URL.format(host=hostname), proxy=proxy)
        country_code = response.json().get("countryCode", "UNKNOWN")
    except Exception:
        country_code = "UNKNOWN"

    await set_geoip_cache(hostname, country_code)
    return country_code == "BR"
