from linksurf.common.constants import MIN_QUEUE_PRIORITY, MAX_QUEUE_PRIORITY
from linksurf.common.payload import Payload
from linksurf.common.types import Error
from linksurf.components.base import Prioritizer, PrioritizerResponse
from linksurf.services import Services
from linksurf.services.cache import Cache


class MultiFactorPrioritizer(Prioritizer):
    """
    Computes the URL's priority based on a few factors. Priority is higher if:

    - URL has fewer path segments (closer to home)
    - URL has fewer query parameters
    - Domain has lower average request response time
    - Domain has fewer total URLs crawled
    """

    cache: Cache

    def on_start(self, settings, services: Services):
        self.cache = services.cache

    def execute(self, payload: Payload) -> PrioritizerResponse:
        url = payload.url

        try:
            metrics = self.cache.get_domain_metrics(url.domain, url.port)
        except Exception as e:
            return PrioritizerResponse(None, Error("Cache lookup failed.", retriable=True, exception=e))

        scores = [
            self._path_score(url.path_depth),
            self._query_score(url.query),
            self._response_time_score(metrics.avg_response_ms if metrics else None),
            self._crawl_count_score(metrics.total_crawled if metrics else None),
        ]

        priority = round(sum(scores) / len(scores))
        priority = max(MIN_QUEUE_PRIORITY, min(MAX_QUEUE_PRIORITY, priority))

        return PrioritizerResponse(priority, None)

    def _path_score(self, path_depth: int) -> int:
        return max(MIN_QUEUE_PRIORITY, MAX_QUEUE_PRIORITY - path_depth)

    def _query_score(self, query: str) -> int:
        count = len(query.split("&")) if query else 0

        return max(MIN_QUEUE_PRIORITY, MAX_QUEUE_PRIORITY - count)

    def _response_time_score(self, avg_ms: float | None) -> int:
        if avg_ms is None:
            return MAX_QUEUE_PRIORITY // 2

        if avg_ms < 200:
            return 5
        if avg_ms < 500:
            return 4
        if avg_ms < 1000:
            return 3
        if avg_ms < 2000:
            return 2
        if avg_ms < 5000:
            return 1

        return 0

    def _crawl_count_score(self, total_crawled: int | None) -> int:
        if total_crawled is None:
            return MAX_QUEUE_PRIORITY // 2

        if total_crawled < 10:
            return 5
        if total_crawled < 50:
            return 4
        if total_crawled < 200:
            return 3
        if total_crawled < 500:
            return 2
        if total_crawled < 1000:
            return 1

        return 0
