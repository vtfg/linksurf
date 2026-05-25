from __future__ import annotations

from typing import Any

from linksurf.common.models import URL


class Payload:
    def __init__(self, url: URL, priority: int = 0, metadata: dict[str, Any] = None):
        if metadata is None:
            metadata = {}

        self.url = url
        self.priority = priority
        self._metadata = metadata

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
            "metadata": self._metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Payload:
        return cls(
            url=URL(data.get("url")),
            priority=data.get("priority", 0),
            metadata=data.get("metadata", {}),
        )
