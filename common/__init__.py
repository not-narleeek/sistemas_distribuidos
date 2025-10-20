"""Utilities compartidas para la arquitectura asincrónica."""

from .kafka_utils import (
    build_consumer,
    build_producer,
    build_admin_client,
    ensure_topics,
)
from .json_logging import configure_logging
from .mongo import connect_mongo
from .models import (
    QuestionMessage,
    LLMRequest,
    LLMResponse,
    ErrorMessage,
    ValidatedResponse,
)

__all__ = [
    "build_consumer",
    "build_producer",
    "build_admin_client",
    "ensure_topics",
    "configure_logging",
    "connect_mongo",
    "QuestionMessage",
    "LLMRequest",
    "LLMResponse",
    "ErrorMessage",
    "ValidatedResponse",
]
