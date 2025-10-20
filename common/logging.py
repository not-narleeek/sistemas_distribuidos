"""Configuración de logging estructurado."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Mapping


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - logging
        payload: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in logging.LogRecord.__dict__
            and key
            not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelno",
                "levelname",
                "lineno",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }
        }
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | int | None = None) -> None:
    """Configura logging básico en formato JSON."""

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    level = level or os.getenv("LOG_LEVEL", "INFO")
    root.setLevel(level)
