from __future__ import annotations

from dataclasses import asdict
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
            content: Content | None = None,
            redirects: list[Redirect] | None = None,
            request: HTTPRequestSummary | None = None,
            response: HTTPResponseSummary | None = None,
            metadata: dict[str, Any] | None = None,
            storage_id: str | None = None,
            correlation_id: str | None = None,
    ):
        if metadata is None:
            metadata = {}

        self.url = url
        self.priority = priority
        self.retrying = retrying
        self.retries = retries
        self.content = content
        self.redirects: list[Redirect] = redirects or []
        self.request = request
        self.response = response
        self._metadata = metadata
        self.storage_id = storage_id
        self.correlation_id = correlation_id or uuid4().hex

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
            "content": asdict(self.content) if self.content else None,
            "redirects": [asdict(r) for r in self.redirects],
            "request": asdict(self.request) if self.request else None,
            "response": asdict(self.response) if self.response else None,
            "metadata": self._metadata,
            "storage_id": self.storage_id,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Payload:
        content = data.get("content")
        request = data.get("request")
        response = data.get("response")

        return cls(
            url=URL(data["url"]),
            priority=data.get("priority", 0),
            retrying=data.get("retrying", False),
            retries=data.get("retries", 0),
            content=Content(**content) if content else None,
            redirects=[Redirect(**r) for r in data.get("redirects", [])],
            request=HTTPRequestSummary(**request) if request else None,
            response=HTTPResponseSummary(
                **{**response, "redirects": [Redirect(**r) for r in response.get("redirects", [])]}
            ) if response else None,
            metadata=data.get("metadata", {}),
            storage_id=data.get("storage_id"),
            correlation_id=data.get("correlation_id"),
        )
