from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiosqlite

from linksurf.common.models import URL, CrawlStatus
from linksurf.common.settings import Settings
from linksurf.events import Event
from linksurf.events.listeners import Listener
from linksurf.services import Services, Service

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

        _client: aiosqlite.Connection = None

        ROOT_NODE = "/"

        def __init__(self):
            super().__init__()

            self._lock = asyncio.Lock()

        async def on_start(self, settings: Settings):
            self._client = await aiosqlite.connect("visualization.db")
            self._client.row_factory = aiosqlite.Row

            # WAL lets others applications read the file while writing
            await self._client.execute("PRAGMA journal_mode = WAL")

            # a cluster represents a netloc ("example.com", "example.com:8080")
            # scheme is left out because most websites redirect http to https
            # port is kept (if different from default) because can point to a different service
            await self._client.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            """)

            # a node represents a resource (HTML, PDF, etc.)
            await self._client.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                    UNIQUE (cluster_id, name)
                )
            """)

            await self._client.commit()

        async def on_stop(self):
            if self._client is not None:
                await self._client.close()

        async def upsert_node(self, url: URL, status: CrawlStatus | str = CrawlStatus.PENDING):
            """
            Places a page in its cluster's tree, creating the cluster's root on first sight.

            A page hangs off its nearest *existing* ancestor, since intermediate paths only become nodes once they're crawled.
            The tree is recomputed based on the prefix.
            """

            if self._client is None:
                raise RuntimeError("Service not started.")

            name = self._node_name(url)
            status = str(status)

            async with self._lock:
                cluster_id = await self._upsert_cluster(url.netloc)

                if name == self.ROOT_NODE:
                    await self._upsert_root(cluster_id, status)

                    await self._client.commit()

                    return

                root_id = await self._upsert_root(cluster_id)

                async with self._client.execute(
                        "SELECT id, parent_id FROM nodes WHERE cluster_id = ? AND name = ?",
                        (cluster_id, name)) as cursor:
                    existing = await cursor.fetchone()

                # already placed in the tree, so only the status can have changed
                # ignores if node's status is succeeded, which means a URL collapsing to the same node don't move it back to pending
                # can happen if http URL redirects to https keeping the same path when the https version was already successfully crawled
                if existing is not None and existing["parent_id"] is not None:
                    await self._client.execute(
                        "UPDATE nodes SET status = ? WHERE id = ? AND status != ?",
                        (status, existing["id"], CrawlStatus.SUCCEEDED.value))

                    await self._client.commit()

                    return

                parent_id = await self._find_parent(cluster_id, name, root_id)

                # the parent is always taken, but a succeeded status is kept. The update has to fire
                # either way, otherwise RETURNING yields no row to adopt the descendants with
                async with self._client.execute("""
                    INSERT INTO nodes (name, cluster_id, status, parent_id) VALUES (?, ?, ?, ?)
                    ON CONFLICT(cluster_id, name)
                    DO UPDATE SET
                        parent_id = excluded.parent_id,
                        status = CASE WHEN nodes.status = ? THEN nodes.status ELSE excluded.status END
                    RETURNING id
                """, (name, cluster_id, status, parent_id, CrawlStatus.SUCCEEDED.value)) as cursor:
                    node_id = (await cursor.fetchone())["id"]

                await self._adopt_descendants(cluster_id, name, node_id)

                await self._client.commit()

        async def _upsert_cluster(self, netloc: str) -> int:
            """
            Upserts and returns the id of the cluster holding `netloc`.
            """

            async with self._client.execute("""
                INSERT INTO clusters (name) VALUES (?)
                ON CONFLICT(name) DO UPDATE SET name = excluded.name
                RETURNING id
            """, (netloc,)) as cursor:
                return (await cursor.fetchone())["id"]

        async def _upsert_root(self, cluster_id: int, status: str | None = None) -> int:
            """
            Upserts and returns the cluster's root ("/") node id.

            The root is virtual: it anchors the cluster's tree whether it is crawled or even exists.
            """

            async with self._client.execute("""
                INSERT INTO nodes (name, cluster_id, status, parent_id) VALUES (?, ?, ?, NULL)
                ON CONFLICT(cluster_id, name)
                DO UPDATE SET
                    status = CASE WHEN nodes.status = ? THEN nodes.status ELSE COALESCE(?, nodes.status) END
                RETURNING id
            """, (self.ROOT_NODE, cluster_id, status or CrawlStatus.PENDING.value,
                  CrawlStatus.SUCCEEDED.value, status)) as cursor:
                return (await cursor.fetchone())["id"]

        async def _find_parent(self, cluster_id: int, name: str, root_id: int) -> int:
            """
            Returns the id of the directory holding this node, or the nearest one that exists.

            Ordering by length is what picks the nearest: a deeper directory is always a longer
            string, and a directory is exactly one character longer than its own page form, so
            "/products/" wins over "/products" when both were crawled.
            """

            ancestors = self._ancestor_names(name)
            placeholders = ", ".join("?" * len(ancestors))

            async with self._client.execute(f"""
                SELECT id FROM nodes
                WHERE cluster_id = ? AND name IN ({placeholders})
                ORDER BY LENGTH(name) DESC
                LIMIT 1
            """, (cluster_id, *ancestors)) as cursor:
                row = await cursor.fetchone()

            return row["id"] if row is not None else root_id

        async def _adopt_descendants(self, cluster_id: int, name: str, node_id: int) -> None:
            """
            Hands this node every descendant that settled on a farther ancestor before it existed.

            Only descendants whose current parent is shallower than this node are taken: one
            already hanging off a deeper directory keeps it, since that parent is the nearer of the two.
            """

            # a page holds whatever its directory form would hold, so "/products" can adopt
            # "/products/nike" when "/products/" itself was never crawled. The prefix itself is
            # excluded: "/products" and "/products/" are two resources side by side, not nested
            prefix = name if name.endswith("/") else f"{name}/"

            # matched with substr() rather than LIKE because "_" is a LIKE wildcard,
            # and it's a perfectly ordinary character in a URL path
            await self._client.execute("""
                UPDATE nodes SET parent_id = ?
                WHERE cluster_id = ?
                  AND substr(name, 1, ?) = ?
                  AND name != ?
                  AND id != ?
                  AND parent_id IN (SELECT id FROM nodes WHERE cluster_id = ? AND LENGTH(name) < ?)
            """, (node_id, cluster_id, len(prefix), prefix, prefix, node_id, cluster_id, len(name)))

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

        self.database = self.VisualizationDatabase()
        self.listener = self.VisualizationListener(self.database)

        application.listeners.append(self.listener)
        application.services.register(self.database)

    async def on_start(self):
        pass

    async def on_stop(self) -> None:
        pass
