"""Modelos de mensajes intercambiados entre servicios."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .kafka_utils import JsonRecord


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass(slots=True)
class QuestionMessage(JsonRecord):
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace_id: str = field(default_factory=_new_trace_id)
    question_id: str = ""
    title: str = ""
    content: str = ""
    best_answer: str = ""
    source: str = "traffic-generator"
    created_at: str = field(default_factory=_now_iso)
    attempts: int = 0


@dataclass(slots=True)
class LLMRequest(JsonRecord):
    message_id: str
    trace_id: str
    question_id: str
    title: str
    content: str
    prompt: str
    best_answer: str
    attempts: int = 0
    created_at: str = field(default_factory=_now_iso)


@dataclass(slots=True)
class LLMResponse(JsonRecord):
    message_id: str
    trace_id: str
    question_id: str
    title: str
    content: str
    prompt: str
    llm_answer: str
    best_answer: str
    latency_ms: float
    attempts: int
    produced_at: str = field(default_factory=_now_iso)


@dataclass(slots=True)
class ErrorMessage(JsonRecord):
    message_id: str
    trace_id: str
    question_id: str
    error_type: str
    error_detail: str
    attempts: int
    retry_at: str | None = None
    produced_at: str = field(default_factory=_now_iso)


@dataclass(slots=True)
class ValidatedResponse(JsonRecord):
    message_id: str
    trace_id: str
    question_id: str
    title: str
    content: str
    llm_answer: str
    best_answer: str
    score: float
    accepted: bool
    source: str
    attempts: int
    decided_at: str = field(default_factory=_now_iso)
