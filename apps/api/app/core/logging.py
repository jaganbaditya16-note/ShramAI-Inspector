"""Structured JSON logging with request-scoped context.

Design goals:
- Machine-parseable single-line JSON logs for aggregation.
- Request/job/case/document identifiers attached via contextvars.
- Never log request bodies or extracted document content.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key in ("event", "method", "path", "status", "duration_ms", "client_ip"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.levelname:<7} {record.getMessage()}"
        rid = request_id_var.get()
        if rid and rid != "-":
            base = f"[{rid}] {base}"
        if record.exc_info and record.exc_info[0] is not None:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if log_format == "json" else ConsoleFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Align third-party loggers with our handler.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
