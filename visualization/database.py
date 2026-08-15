from typing import Optional

from sqlalchemy import Enum, Column
from sqlmodel import Field, SQLModel, UniqueConstraint, Relationship

from linksurf.common.models import CrawlStatus as NodeStatus


class Cluster(SQLModel, table=True):
    """
    A cluster represents a netloc (example.com, example.com:8080) and serves to group nodes within the graph visualization.

    The URL's scheme is left out of the cluster's name because most websites redirect HTTP to HTTPS with the same path.
    If included, crawling HTTP URLs in a domain that also serves HTTPS would create a new cluster full of nodes with status `REDIRECTED`.
    """

    __tablename__ = "clusters"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)

    nodes: list["Node"] = Relationship(back_populates="cluster")


class Node(SQLModel, table=True):
    """
    A node represents a resource (HTML, PDF, etc.) inside a cluster.
    """

    __tablename__ = "nodes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    status: NodeStatus = Field(
        sa_column=Column(Enum(NodeStatus, native_enum=False, nullable=False,
                              values_callable=lambda enum: [str(m.value) for m in enum])),
    )

    cluster_id: Optional[int] = Field(default=None, foreign_key="clusters.id", index=True)
    cluster: Cluster = Relationship(back_populates="nodes")

    parent_id: Optional[int] = Field(default=None, foreign_key="nodes.id")

    __table_args__ = (
        UniqueConstraint("name", "cluster_id", name="unique_name_per_cluster"),
    )
