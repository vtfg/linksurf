from __future__ import annotations

import site
from typing import Any

import structlog


class Logger:
    _instance: Logger | None = None

    def __new__(cls) -> Logger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()

        return cls._instance

    def _setup(self) -> None:
        site_packages = site.getsitepackages()

        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper("iso", utc=True),
                structlog.dev.ConsoleRenderer(
                    exception_formatter=structlog.dev.RichTracebackFormatter(
                        show_locals=True,
                        max_frames=2,
                        suppress=site_packages
                    ),
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
