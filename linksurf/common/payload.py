from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from linksurf.common.models import URL, Content, HTTPResponseSummary, HTTPRequestSummary, Redirect


class Payload:
    def __init__(
            self,
            url: URL,
            priority: int = 0,
            retrying: bool = False,
            retries: int = 0,
            deduplicated: bool = False,
            content: Content | None = None,
            redirects: list[Redirect] | None = None,
            request: HTTPRequestSummary | None = None,
            response: HTTPResponseSummary | None = None,
            metadata: dict[str, Any] | None = None,
            correlation_id: str | None = None,
            crawl_id: str | None = None,
            discovered_at: datetime = datetime.now(timezone.utc),
    ):
        if metadata is None:
            metadata = {}

        self.url = url
        self.priority = priority
        self.retrying = retrying
        self.retries = retries
        self.deduplicated = deduplicated
        self.content = content
        self.redirects: list[Redirect] = redirects or []
        self.request = request
        self.response = response
        self._metadata = metadata
        self.correlation_id = correlation_id or uuid4().hex
        self.crawl_id = crawl_id
        self.discovered_at = discovered_at

        # TODO: Remove this workaround
        # in-memory only, never serialized
        # tracks if this Payload was handed onward to the next pipeline stage
        # must be set explicitly before publishing to another component
        # used inside the Component's execution saving logic
        self.published = False

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata

    def get_metadata(self, key: str) -> Any:
        return self._metadata.get(key)

    def add_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url.address,
            "priority": self.priority,
            "retrying": self.retrying,
            "retries": self.retries,
            "deduplicated": self.deduplicated,
            "content": asdict(self.content) if self.content else None,
            "redirects": [asdict(r) for r in self.redirects],
            "request": asdict(self.request) if self.request else None,
            "response": asdict(self.response) if self.response else None,
            "metadata": self._metadata,
            "correlation_id": self.correlation_id,
            "crawl_id": self.crawl_id,
            "discovered_at": self.discovered_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Payload:
        content = data.get("content")
        request = data.get("request")
        response = data.get("response")
        discovered_at = data.get("discovered_at")

        return cls(
            url=URL(data["url"]),
            priority=data.get("priority", 0),
            retrying=data.get("retrying", False),
            retries=data.get("retries", 0),
            deduplicated=data.get("deduplicated", False),
            content=Content(**content) if content else None,
            redirects=[Redirect(**r) for r in data.get("redirects", [])],
            request=HTTPRequestSummary(**request) if request else None,
            response=HTTPResponseSummary(
                **{**response, "redirects": [Redirect(**r) for r in response.get("redirects", [])]}
            ) if response else None,
            metadata=data.get("metadata", {}),
            correlation_id=data.get("correlation_id"),
            crawl_id=data.get("crawl_id"),
            discovered_at=datetime.fromisoformat(str(discovered_at)) if discovered_at else datetime.now(timezone.utc),
        )
