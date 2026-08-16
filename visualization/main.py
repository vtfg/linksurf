import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Annotated, Union
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.templating import Jinja2Templates
from pydantic import Field
from sqlalchemy.orm import aliased
from sqlmodel import Session, SQLModel, col, create_engine, select, func

from linksurf.events import CrawlFinishEvent, CrawlPendingEvent, CrawlStartEvent
from linksurf.utils.env import get_env
from visualization.constants import ROOT_NODE
from visualization.database import Cluster, Node, NodeStatus
from visualization.utils import node_name, ancestor_names

PACKAGE_DIR = Path(__file__).resolve().parent

load_dotenv(PACKAGE_DIR / ".env")

engine = create_engine(get_env("DATABASE_URL"), echo=True)

CrawlEvent = Annotated[
    Union[CrawlPendingEvent, CrawlStartEvent, CrawlFinishEvent],
    Field(discriminator="name"),
]

# only CrawlFinishEvent carries a status, the other two are implied by the event itself
STATUS_BY_EVENT = {
    "crawl.pending": NodeStatus.PENDING,
    "crawl.start": NodeStatus.IN_PROGRESS,
}

app = FastAPI()

templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

# one queue per connected browser. A slow client fills its own and starts losing updates
# without holding anyone else up - it resyncs from /api/graph when it notices the gap
subscribers: set[asyncio.Queue] = set()
event_loop: asyncio.AbstractEventLoop | None = None

MAX_PENDING_UPDATES = 1_000

# how long an idle stream waits before looping round to check the browser is still there
DISCONNECT_CHECK_SECONDS = 15


@app.on_event("startup")
async def on_startup():
    global event_loop

    # send_event runs in a threadpool, so handing an update to the subscribers means crossing
    # back onto the loop; this is where that loop can be captured
    event_loop = asyncio.get_running_loop()

    SQLModel.metadata.create_all(engine)


def node_update(node: Node) -> dict:
    """
    A node as the canvas consumes it, minus the depth: that follows from the parent, which the
    browser already holds, and a re-parenting shifts a whole subtree's worth of them at once.
    """

    return {
        "id": node.id,
        "cluster_id": node.cluster_id,
        "parent": node.parent_id,
        "name": node.name,
        "status": str(node.status),
    }


def broadcast(clusters: list[dict], nodes: list[dict]) -> None:
    """
    Hands every connected browser what this request changed.

    Called from the threadpool send_event runs in, so each delivery is scheduled onto the loop
    rather than touching the queues directly.
    """

    if not nodes or event_loop is None or not subscribers:
        return

    update = {"clusters": clusters, "nodes": nodes}

    def deliver(queue: asyncio.Queue) -> None:
        try:
            queue.put_nowait(update)
        except asyncio.QueueFull:
            pass  # this browser is behind; the gap makes it reload the whole graph

    for queue in list(subscribers):
        event_loop.call_soon_threadsafe(deliver, queue)


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/health")
def health():
    return "ok"


@app.get("/api/graph")
def get_graph():
    with Session(engine) as session:
        rows = session.exec(
            select(Node.id, Node.name, Node.status, Node.parent_id, Cluster.id, Cluster.name)
            .join(Cluster, col(Node.cluster_id) == Cluster.id)
            .order_by(col(Node.id))
        ).all()

    children = defaultdict(list)
    roots = []

    for node_id, _, _, parent_id, _, _ in rows:
        if parent_id is None:
            roots.append(node_id)
        else:
            children[parent_id].append(node_id)

    # depth follows the edges the canvas actually draws: a page whose intermediate directories
    # were never crawled hangs off a nearer ancestor, and its ring has to match that edge
    depths = {}
    queue = deque((node_id, 0) for node_id in roots)

    while queue:
        node_id, depth = queue.popleft()

        depths[node_id] = depth

        for child in children[node_id]:
            queue.append((child, depth + 1))

    clusters: dict[int, dict] = {}
    nodes = []

    for node_id, name, status, parent_id, cluster_id, cluster_name in rows:
        depth = depths.get(node_id, 0)

        cluster = clusters.setdefault(
            cluster_id, {"id": cluster_id, "name": cluster_name, "count": 0, "maxDepth": 0})
        cluster["count"] += 1
        cluster["maxDepth"] = max(cluster["maxDepth"], depth)

        nodes.append({
            "id": node_id,
            "cluster_id": cluster_id,
            "parent": parent_id,
            "name": name,
            "depth": depth,
            "status": status,
        })

    return {"clusters": list(clusters.values()), "nodes": nodes}


@app.post("/api/event")
def send_event(event: CrawlEvent):
    netloc = urlsplit(event.url).netloc
    name = node_name(event.url)
    status = getattr(event, "status", None) or STATUS_BY_EVENT.get(event.name, NodeStatus.PENDING)

    # everything this request creates or moves, so a browser can apply it without refetching.
    # The cluster and the root are included when they are made here, since nothing else will
    # ever announce them
    created_clusters: list[dict] = []
    updates: dict[int, dict] = {}

    with Session(engine) as session:
        cluster = session.exec(select(Cluster).where(Cluster.name == netloc)).first()

        if cluster is None:
            cluster = Cluster(name=netloc)

            session.add(cluster)
            session.commit()
            session.refresh(cluster)

            created_clusters.append({"id": cluster.id, "name": cluster.name})

        # the root is virtual: it anchors the cluster's tree whether it is crawled or even exists.
        root = session.exec(
            select(Node).where(Node.cluster_id == cluster.id, Node.name == ROOT_NODE)).first()

        if root is None:
            root = Node(name=ROOT_NODE, cluster_id=cluster.id, status=NodeStatus.PENDING)

            session.add(root)
            session.commit()
            session.refresh(root)

            updates[root.id] = node_update(root)

        node = root if name == ROOT_NODE else session.exec(
            select(Node).where(Node.cluster_id == cluster.id, Node.name == name)).first()

        # already placed in the tree, so only the status can have changed
        # ignores if node's status is succeeded, which means a URL collapsing to the same node don't move it back to pending
        # can happen if HTTP URL redirects to HTTPS keeping the same path when the HTTPS version was already successfully crawled
        if node is not None and (node is root or node.parent_id is not None):
            if node.status != NodeStatus.SUCCEEDED:
                node.status = status

                session.add(node)
                session.commit()
                session.refresh(node)

                updates[node.id] = node_update(node)

            broadcast(created_clusters, list(updates.values()))

            return node

        # the node's nearest existing ancestor, falling back to the root. Ordering by length is
        # what picks the nearest: a deeper directory is always a longer string, and a directory is
        # exactly one character longer than its own page form, so "/products/" wins over "/products"
        parent = session.exec(
            select(Node)
            .where(Node.cluster_id == cluster.id, col(Node.name).in_(ancestor_names(name)))
            .order_by(func.length(Node.name).desc())
        ).first()

        parent_id = parent.id if parent is not None else root.id

        if node is None:
            node = Node(name=name, cluster_id=cluster.id, status=status, parent_id=parent_id)
        else:
            # the parent is always taken, but a succeeded status is kept
            node.parent_id = parent_id

            if node.status != NodeStatus.SUCCEEDED:
                node.status = status

        session.add(node)
        session.commit()
        session.refresh(node)

        # hand this node every descendant that settled on a farther ancestor before it existed.
        # only descendants whose current parent is shallower are taken: one already hanging off a
        # deeper directory keeps it, since that parent is the nearer of the two.

        # a page holds whatever its directory form would hold, so "/products" can adopt
        # "/products/nike" when "/products/" itself was never crawled. The prefix itself is
        # excluded: "/products" and "/products/" are two resources side by side, not nested
        prefix = name if name.endswith("/") else f"{name}/"

        current_parent = aliased(Node)

        descendants = session.exec(
            select(Node)
            .join(current_parent, col(Node.parent_id) == current_parent.id)
            .where(
                Node.cluster_id == cluster.id,
                # autoescape because "_" is a LIKE wildcard and an ordinary character in a path
                col(Node.name).startswith(prefix, autoescape=True),
                Node.name != prefix,
                Node.id != node.id,
                func.length(current_parent.name) < len(name),
            )
        ).all()

        for descendant in descendants:
            descendant.parent_id = node.id

            session.add(descendant)

        session.commit()
        session.refresh(node)

        updates[node.id] = node_update(node)

        # an adoption moves edges the browser already drew, so the moved nodes have to travel
        # with the new one - otherwise its tree keeps the old parents and quietly diverges
        for descendant in descendants:
            session.refresh(descendant)

            updates[descendant.id] = node_update(descendant)

        broadcast(created_clusters, list(updates.values()))

        return node


@app.get("/api/stream", response_class=EventSourceResponse)
async def stream_updates(request: Request) -> AsyncIterable[ServerSentEvent]:
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=MAX_PENDING_UPDATES)

    subscribers.add(queue)

    try:
        while not await request.is_disconnected():
            try:
                update = await asyncio.wait_for(queue.get(), timeout=DISCONNECT_CHECK_SECONDS)
            except TimeoutError:
                continue

            yield ServerSentEvent(event="graph", data=update)
    finally:
        subscribers.discard(queue)


if __name__ == "__main__":
    import os
    import uvicorn

    current_dir = os.path.dirname(os.path.abspath(__file__))

    uvicorn.run("main:app", host="localhost", port=8000, reload=True, reload_dirs=[current_dir])
