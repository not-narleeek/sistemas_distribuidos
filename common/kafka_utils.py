"""Abstracciones comunes para trabajar con Apache Kafka."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from typing import Callable, Iterable, Mapping, MutableMapping, Optional, TypeVar

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.admin import NewTopic
from kafka.errors import KafkaError, NoBrokersAvailable

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _connect_with_retry(factory: Callable[[], T], *, resource: str) -> T:
    """Intenta construir un recurso de Kafka con reintentos."""

    attempts = int(os.getenv("KAFKA_CONNECT_ATTEMPTS", "15"))
    backoff = float(os.getenv("KAFKA_CONNECT_BACKOFF", "2.0"))
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return factory()
        except (NoBrokersAvailable, KafkaError) as exc:  # pragma: no cover - dependiente del broker
            last_exc = exc
            LOGGER.warning(
                "%s no disponible aún, reintentando",
                resource,
                extra={"attempt": attempt, "max_attempts": attempts},
            )
            time.sleep(backoff)
    assert last_exc is not None
    LOGGER.error("Imposible conectar con %s después de %s intentos", resource, attempts)
    raise last_exc


def _base_config() -> dict[str, object]:
    return {
        "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "client_id": os.getenv("SERVICE_NAME", "distributed-system"),
    }


def build_producer(**overrides: object) -> KafkaProducer:
    """Crea un productor configurado para garantizar idempotencia."""

    config: MutableMapping[str, object] = {
        "enable_idempotence": True,
        "acks": "all",
        "linger_ms": 5,
        "retries": 5,
        "max_in_flight_requests_per_connection": 1,
        "value_serializer": lambda value: json.dumps(value).encode("utf-8"),
        "key_serializer": lambda value: value.encode("utf-8") if value is not None else None,
    }
    config.update(_base_config())
    config.update(overrides)
    return _connect_with_retry(lambda: KafkaProducer(**config), resource="KafkaProducer")


def build_consumer(
    topic: str,
    group_id: str,
    *,
    value_deserializer: Optional[callable] = None,
    **overrides: object,
) -> KafkaConsumer:
    """Construye un consumidor configurado con commits seguros."""

    if value_deserializer is None:
        value_deserializer = lambda value: json.loads(value.decode("utf-8"))

    config: MutableMapping[str, object] = {
        "group_id": group_id,
        "auto_offset_reset": "earliest",
        "enable_auto_commit": False,
        "value_deserializer": value_deserializer,
        "key_deserializer": lambda value: value.decode("utf-8") if value is not None else None,
        "consumer_timeout_ms": int(os.getenv("KAFKA_CONSUMER_TIMEOUT_MS", "1000")),
        "max_poll_records": int(os.getenv("KAFKA_MAX_POLL_RECORDS", "50")),
    }
    config.update(_base_config())
    config.update(overrides)
    consumer = _connect_with_retry(lambda: KafkaConsumer(**config), resource="KafkaConsumer")
    if topic:
        consumer.subscribe([topic])
    return consumer


def build_admin_client(**overrides: object) -> KafkaAdminClient:
    config: MutableMapping[str, object] = {}
    config.update(_base_config())
    config.update(overrides)
    return _connect_with_retry(lambda: KafkaAdminClient(**config), resource="KafkaAdminClient")


def ensure_topics(topics: Iterable[NewTopic]) -> None:
    """Crea los tópicos indicados si aún no existen."""

    admin = build_admin_client()
    existing = admin.list_topics()
    new_topics = [topic for topic in topics if topic.name not in existing]
    if not new_topics:
        LOGGER.info("No hay tópicos nuevos por crear")
        return
    try:
        admin.create_topics(new_topics=new_topics, validate_only=False)
        LOGGER.info("Tópicos creados: %s", ", ".join(topic.name for topic in new_topics))
    except Exception as exc:  # pragma: no cover - dependiente del broker
        LOGGER.warning("No fue posible crear tópicos: %s", exc)
    finally:
        admin.close()


def produce_dataclass(producer: KafkaProducer, topic: str, payload) -> None:
    """Envía un dataclass serializado como JSON."""

    if hasattr(payload, "asdict"):
        record = payload.asdict()
    else:
        record = asdict(payload)
    key = str(record.get("message_id")) if record.get("message_id") else None
    producer.send(topic, key=key, value=record)
    producer.flush()


class JsonRecord:
    """Mixin para serializar dataclasses a diccionarios."""

    def asdict(self) -> Mapping[str, object]:
        return asdict(self)
