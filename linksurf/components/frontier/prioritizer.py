from linksurf.common.payload import Payload
from linksurf.components.base import Prioritizer, PrioritizerResponse
from linksurf.services import Database, Cache, Services


# Computes a page priority based on some factors. Priority increases if:
# 1. Fewer path segments (closer to home)
# 2. Fewer query parameters
# 3. Lower average request response time
# 4. Fewer total URLs crawled for domain
class MultiFactorPrioritizer(Prioritizer):
    database: Database
    cache: Cache

    def on_start(self, services: Services):
        self.database = services.database
        self.cache = services.cache

    def execute(self, payload: Payload) -> PrioritizerResponse:
        return PrioritizerResponse(0, None)
