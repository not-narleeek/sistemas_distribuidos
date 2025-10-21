"""Utilidades compartidas para conectarse a MongoDB con reintentos."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

LOGGER = logging.getLogger(__name__)


def connect_mongo(
    uri: str,
    *,
    server_selection_timeout_ms: int = 5000,
    attempts: int | None = None,
    backoff_seconds: float | None = None,
    **kwargs: Any,
) -> MongoClient:
    """Construye un cliente de MongoDB asegurando disponibilidad."""

    max_attempts = attempts or int(os.getenv("MONGO_MAX_ATTEMPTS", "15"))
    backoff = backoff_seconds or float(os.getenv("MONGO_BACKOFF_SECONDS", "2.0"))
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            client = MongoClient(
                uri,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
                **kwargs,
            )
            client.admin.command("ping")
            return client
        except PyMongoError as exc:  # pragma: no cover - depende del servicio externo
            last_exc = exc
            LOGGER.warning(
                "MongoDB no disponible aún, reintentando",
                extra={"attempt": attempt, "max_attempts": max_attempts},
            )
            time.sleep(backoff)
    assert last_exc is not None
    LOGGER.error(
        "Imposible establecer conexión con MongoDB tras %s intentos",
        max_attempts,
    )
    raise last_exc
