import math
from urllib.parse import parse_qsl, urlsplit

from linksurf.constants import QUEUE_MAX_PRIORITY
from linksurf.manager.cache import get_domain_stats
from linksurf.helpers import get_domain_name, get_root_domain

_MAX_RESPONSE_TIME_MS = 5000.0


class Prioritizer:
    async def score(self, url: str) -> int:
        parsed = urlsplit(url)
        domain = get_domain_name(url)

        # Factor 1: fewer path segments = closer to home page = higher priority
        segments = [s for s in parsed.path.split("/") if s]
        f1 = 1.0 / (1 + len(segments))

        # Factor 2: fewer query params = higher priority
        params = parse_qsl(parsed.query)
        f2 = 1.0 / (1 + len(params))

        # Factor 3: root domain novelty — subdomains share the same crawl count
        root_domain = get_root_domain(url)
        root_data = await get_domain_stats(root_domain)
        total = int(root_data.get("total_crawled_urls", 0))

        if total == 0:
            return QUEUE_MAX_PRIORITY

        f3 = 1.0 / (1 + math.log1p(total))

        # Factor 4: per-subdomain avg response time (servers may differ)
        domain_data = await get_domain_stats(domain)
        avg_response = float(domain_data.get("avg_response_time", 0))
        f4 = max(0.0, 1.0 - avg_response / _MAX_RESPONSE_TIME_MS)

        combined = (f1 + f2 + f3 + f4) / 4.0

        priority = round(combined * QUEUE_MAX_PRIORITY)

        return priority
