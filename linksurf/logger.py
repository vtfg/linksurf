from __future__ import annotations

from typing import Any

import structlog


class Logger:
    _instance: Logger | None = None

    def __new__(cls) -> Logger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()

        return cls._instance

    @staticmethod
    def _drop_correlation_id(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.pop("correlation_id", None)

        return event_dict

    def _setup(self) -> None:
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper("iso", utc=True),
                self._drop_correlation_id,
                structlog.dev.ConsoleRenderer(
                    exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=True)
                ),
            ],
        )

        self._log = structlog.get_logger()

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._log.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log.error(event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        self._log.exception(event, **kwargs)
