from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg

from linksurf.common.models import URL, CrawlStatus
from linksurf.common.settings import Settings
from linksurf.events import Event
from linksurf.events.listeners import Listener
from linksurf.services import Services, Service
from linksurf.utils.env import get_env

if TYPE_CHECKING:
    from linksurf.application import Linksurf


class Extension:
    """
    Increment the application's behavior by implementing new components, services and listeners,
    and also define new elements (rules, middlewares, filters, etc.) for the existing components.

    They serve as a drop-in behavior change that allows grouping related modifications in a single file.

    Extensions can be HTTP servers, like an Admin Panel that shows metrics about the crawler,
    or implement lifecycle events/scheduled events (e.g. to check proxies periodically).
    """

    # TODO: Create application callbacks so extensions can inject data into payloads or requests objects.
    # ^ Useful for user-agent rotation or proxy pool extensions.

    def __init__(self, application: Linksurf, settings: Settings, services: Services):
        """
        Function used to inject all components needed for the extension into the application.
        """

        self.application = application

    async def on_start(self):
        """
        Function used to start the extension and its required components (which were not injected).

        "Start" in this context means creating any database connection or requesting required data asynchronously, for example.
        """

        raise NotImplementedError()

    async def on_stop(self):
        """
        Function used to gracefully stop the extension and its required components (which were not injected).
        """

        raise NotImplementedError()


class VisualizationExtension(Extension):
    """
    Defines all components required for visualizing crawls in real-time.

    Used for project presentation only, as it reduces the overall performance.

    Visualization is stored as a force-directed graph network. Each cluster represents a domain, and nodes as its pages.
    The relationship follows the domain's directory structure.
    """

    class VisualizationDatabase(Service):
        NAME = "VisualizationDatabase"

        ROOT_NODE = "/"

        def __init__(self, url: str):
            super().__init__()

            self.url = url
            self._lock = asyncio.Lock()
            self._pool: asyncpg.Pool | None = None

        async def on_start(self, settings: Settings):
            pool = await asyncpg.create_pool(self.url, min_size=1, max_size=10)

            # a cluster represents a netloc ("example.com", "example.com:8080")
            # scheme is left out because most websites redirect http to https
            # port is kept (if different from default) because can point to a different service
            async with pool.acquire() as connection:
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS clusters (
                        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE
                    )
                """)

                # a node represents a resource (HTML, PDF, etc.)
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS nodes (
                        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        name TEXT NOT NULL,
                        cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
                        status TEXT NOT NULL,
                        parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                        UNIQUE (cluster_id, name)
                    )
                """)

            self._pool = pool

        async def on_stop(self):
            if self._pool is not None:
                await self._pool.close()

        async def upsert_node(self, url: URL, status: CrawlStatus | str = CrawlStatus.PENDING):
            """
            Places a page in its cluster's tree, creating the cluster's root on first sight.

            A page hangs off its nearest *existing* ancestor, since intermediate paths only become nodes once they're crawled.
            The tree is recomputed based on the prefix.
            """

            if self._pool is None:
                raise RuntimeError("Service not started.")

            name = self._node_name(url)
            status = str(status)

            async with self._lock, self._pool.acquire() as connection, connection.transaction():
                cluster_id = await self._upsert_cluster(connection, url.netloc)

                if name == self.ROOT_NODE:
                    await self._upsert_root(connection, cluster_id, status)

                    return

                root_id = await self._upsert_root(connection, cluster_id)

                existing = await connection.fetchrow(
                    "SELECT id, parent_id FROM nodes WHERE cluster_id = $1 AND name = $2",
                    cluster_id, name)

                # already placed in the tree, so only the status can have changed
                # ignores if node's status is succeeded, which means a URL collapsing to the same node don't move it back to pending
                # can happen if http URL redirects to https keeping the same path when the https version was already successfully crawled
                if existing is not None and existing["parent_id"] is not None:
                    await connection.execute(
                        "UPDATE nodes SET status = $1 WHERE id = $2 AND status != $3",
                        status, existing["id"], CrawlStatus.SUCCEEDED.value)

                    return

                parent_id = await self._find_parent(connection, cluster_id, name, root_id)

                # the parent is always taken, but a succeeded status is kept. The update has to fire
                # either way, otherwise RETURNING yields no row to adopt the descendants with
                node_id = await connection.fetchval("""
                    INSERT INTO nodes (name, cluster_id, status, parent_id) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (cluster_id, name)
                    DO UPDATE SET
                        parent_id = excluded.parent_id,
                        status = CASE WHEN nodes.status = $5 THEN nodes.status ELSE excluded.status END
                    RETURNING id
                """, name, cluster_id, status, parent_id, CrawlStatus.SUCCEEDED.value)

                await self._adopt_descendants(connection, cluster_id, name, node_id)

        async def _upsert_cluster(self, connection: asyncpg.Connection, netloc: str) -> int:
            """
            Upserts and returns the id of the cluster holding `netloc`.
            """

            return await connection.fetchval("""
                INSERT INTO clusters (name) VALUES ($1)
                ON CONFLICT (name) DO UPDATE SET name = excluded.name
                RETURNING id
            """, netloc)

        async def _upsert_root(self, connection: asyncpg.Connection, cluster_id: int,
                               status: str | None = None) -> int:
            """
            Upserts and returns the cluster's root ("/") node id.

            The root is virtual: it anchors the cluster's tree whether it is crawled or even exists.
            """

            return await connection.fetchval("""
                INSERT INTO nodes (name, cluster_id, status, parent_id) VALUES ($1, $2, $3, NULL)
                ON CONFLICT (cluster_id, name)
                DO UPDATE SET
                    status = CASE WHEN nodes.status = $4 THEN nodes.status ELSE COALESCE($5, nodes.status) END
                RETURNING id
            """, self.ROOT_NODE, cluster_id, status or CrawlStatus.PENDING.value,
                                             CrawlStatus.SUCCEEDED.value, status)

        async def _find_parent(self, connection: asyncpg.Connection, cluster_id: int, name: str,
                               root_id: int) -> int:
            """
            Returns the id of the directory holding this node, or the nearest one that exists.

            Ordering by length is what picks the nearest: a deeper directory is always a longer
            string, and a directory is exactly one character longer than its own page form, so
            "/products/" wins over "/products" when both were crawled.
            """

            parent_id = await connection.fetchval("""
                SELECT id FROM nodes
                WHERE cluster_id = $1 AND name = ANY($2::text[])
                ORDER BY LENGTH(name) DESC
                LIMIT 1
            """, cluster_id, self._ancestor_names(name))

            return parent_id if parent_id is not None else root_id

        async def _adopt_descendants(self, connection: asyncpg.Connection, cluster_id: int,
                                     name: str, node_id: int) -> None:
            """
            Hands this node every descendant that settled on a farther ancestor before it existed.

            Only descendants whose current parent is shallower than this node are taken: one
            already hanging off a deeper directory keeps it, since that parent is the nearer of the two.
            """

            # a page holds whatever its directory form would hold, so "/products" can adopt
            # "/products/nike" when "/products/" itself was never crawled. The prefix itself is
            # excluded: "/products" and "/products/" are two resources side by side, not nested
            prefix = name if name.endswith("/") else f"{name}/"

            # matched with starts_with() rather than LIKE because "_" is a LIKE wildcard,
            # and it's a perfectly ordinary character in a URL path
            await connection.execute("""
                UPDATE nodes SET parent_id = $1
                WHERE cluster_id = $2
                  AND starts_with(name, $3)
                  AND name != $3
                  AND id != $1
                  AND parent_id IN (SELECT id FROM nodes WHERE cluster_id = $2 AND LENGTH(name) < $4)
            """, node_id, cluster_id, prefix, len(name))

        def _node_name(self, url: URL) -> str:
            """
            A node's identity inside its cluster: the path exactly as served.

            Nothing is stripped. A trailing slash and a file extension can each address an entirely
            different resource, so "/products", "/products/" and "/products.html" are three nodes.
            Query parameters and fragments are already dropped by URL.path.
            """

            return url.path

        def _ancestor_names(self, name: str) -> list[str]:
            """
            Every directory that could hold `name`, nearest first, always ending at the root.

            Ancestry follows the directory structure rather than the string prefix, so a page sits
            under the directory containing it and a directory sits under its parent directory:
            "/products/nike/shoes" and "/products/nike/" both hang off "/products/".

            The page form of each directory comes right after it as a fallback, since sites often
            link "/products" without ever serving "/products/" as a crawlable URL of its own.

            "/products/nike/shoes" -> ["/products/nike/", "/products/nike", "/products/", "/products", "/"]
            """

            ancestors = []
            current = name

            while True:
                stripped = current.rstrip("/")

                if not stripped:
                    break

                directory = stripped[:stripped.rfind("/") + 1]

                if directory == self.ROOT_NODE:
                    break

                ancestors.append(directory)
                ancestors.append(directory.rstrip("/"))

                current = directory

            return ancestors + [self.ROOT_NODE]

    class VisualizationListener(Listener):
        EVENTS = ["crawl.pending", "crawl.start", "crawl.finish"]

        def __init__(self, database: VisualizationExtension.VisualizationDatabase):
            self.database = database

        async def handle(self, event: Event):
            if getattr(event, "url", None) is not None:
                await self.database.upsert_node(URL(event.url), getattr(event, "status", CrawlStatus.PENDING))

    def __init__(self, application: Linksurf, settings: Settings, services: Services):
        super().__init__(application, settings, services)

        self.database = self.VisualizationDatabase(url=get_env("VISUALIZATION_DB_URL"))
        self.listener = self.VisualizationListener(self.database)

        application.listeners.append(self.listener)
        application.services.register(self.database)

    async def on_start(self):
        pass

    async def on_stop(self) -> None:
        pass
