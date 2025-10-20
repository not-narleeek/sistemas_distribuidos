from __future__ import annotations

import argparse
import logging
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any

from common import (
    LLMRequest,
    QuestionMessage,
    ValidatedResponse,
    build_consumer,
    build_producer,
    configure_logging,
    connect_mongo,
)

LOGGER = logging.getLogger(__name__)

from common import (
    LLMRequest,
    QuestionMessage,
    ValidatedResponse,
    build_consumer,
    build_producer,
    configure_logging,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: dict[str, Any]
    stored_at: float


class CacheBase:
    def __init__(self, size: int, ttl: float):
        self.size = size
        self.ttl = ttl
        self.cache: dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:  # pragma: no cover - abstract
        raise NotImplementedError

    def put(self, key: str, value: dict[str, Any]) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def evict(self, key: str) -> None:
        self.cache.pop(key, None)

    def is_expired(self, key: str) -> bool:
        if self.ttl <= 0 or key not in self.cache:
            return False
        return time.time() - self.cache[key].stored_at > self.ttl


class LRUCache(CacheBase):
    def __init__(self, size: int, ttl: float):
        super().__init__(size, ttl)
        self.order = OrderedDict()

    def evict(self, key: str) -> None:
        self.order.pop(key, None)
        super().evict(key)

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self.cache and not self.is_expired(key):
            self.order.move_to_end(key)
            self.hits += 1
            return self.cache[key].value
        if key in self.cache and self.is_expired(key):
            self.evict(key)
        self.misses += 1
        return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        if key in self.cache:
            self.order.move_to_end(key)
        else:
            if len(self.cache) >= self.size:
                oldest, _ = self.order.popitem(last=False)
                super().evict(oldest)
            self.order[key] = None
        self.cache[key] = CacheEntry(value=value, stored_at=time.time())


class LFUCache(CacheBase):
    def __init__(self, size: int, ttl: float):
        super().__init__(size, ttl)
        self.freq = defaultdict(int)

    def evict(self, key: str) -> None:
        self.freq.pop(key, None)
        super().evict(key)

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self.cache and not self.is_expired(key):
            self.freq[key] += 1
            self.hits += 1
            return self.cache[key].value
        if key in self.cache and self.is_expired(key):
            self.evict(key)
        self.misses += 1
        return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        if key not in self.cache and len(self.cache) >= self.size:
            least_used = min(self.freq, key=lambda item: (self.freq[item], self.cache[item].stored_at))
            self.evict(least_used)
        self.cache[key] = CacheEntry(value=value, stored_at=time.time())
        self.freq[key] += 1


class FIFOCache(CacheBase):
    def __init__(self, size: int, ttl: float):
        super().__init__(size, ttl)
        self.queue: list[str] = []

    def evict(self, key: str) -> None:
        try:
            self.queue.remove(key)
        except ValueError:
            pass
        super().evict(key)

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self.cache and not self.is_expired(key):
            self.hits += 1
            return self.cache[key].value
        if key in self.cache and self.is_expired(key):
            self.evict(key)
        self.misses += 1
        return None

    def put(self, key: str, value: dict[str, Any]) -> None:
        if key not in self.cache:
            if len(self.cache) >= self.size and self.queue:
                oldest = self.queue.pop(0)
                super().evict(oldest)
            self.queue.append(key)
        self.cache[key] = CacheEntry(value=value, stored_at=time.time())


def build_cache(policy: str, size: int, ttl: float) -> CacheBase:
    if policy == "lru":
        return LRUCache(size, ttl)
    if policy == "lfu":
        return LFUCache(size, ttl)
    if policy == "fifo":
        return FIFOCache(size, ttl)
    raise ValueError(f"Política de caché desconocida: {policy}")


class CacheService:
    def __init__(
        self,
        *,
        policy: str,
        size: int,
        ttl: float,
        mongo_uri: str,
        database: str,
        collection: str,
        input_topic: str,
        llm_topic: str,
        validated_topic: str,
        regeneration_topic: str,
        group_id: str,
    ):
        self.cache = build_cache(policy, size, ttl)
        client = connect_mongo(mongo_uri)
        self.mongo = client[database][collection]
        self.consumer = build_consumer("", group_id=group_id)
        self.consumer.subscribe([input_topic, regeneration_topic])
        self.producer = build_producer()
        self.llm_topic = llm_topic
        self.validated_topic = validated_topic
        self.regen_topic = regeneration_topic

    def _lookup_storage(self, question_id: str) -> dict[str, Any] | None:
        record = self.mongo.find_one({"id_pregunta": question_id})
        if not record or not record.get("respuesta_llm"):
            return None
        return {
            "question_id": question_id,
            "llm_answer": record.get("respuesta_llm", ""),
            "best_answer": record.get("respuesta_dataset", ""),
            "score": float(record.get("score", 0.0)),
            "accepted": bool(record.get("aceptado", False)),
            "title": record.get("pregunta", ""),
            "content": record.get("contenido", ""),
        }

    def _emit_validated(self, message: QuestionMessage, cached: dict[str, Any], source: str) -> None:
        validated = ValidatedResponse(
            message_id=message.message_id,
            trace_id=message.trace_id,
            question_id=message.question_id,
            title=cached.get("title", message.title),
            content=cached.get("content", message.content),
            llm_answer=cached.get("llm_answer", ""),
            best_answer=cached.get("best_answer", message.best_answer),
            score=float(cached.get("score", 0.0)),
            accepted=bool(cached.get("accepted", True)),
            source=source,
            attempts=message.attempts,
        )
        self.producer.send(self.validated_topic, key=validated.message_id, value=validated.asdict())
        self.producer.flush()

    def _emit_llm_request(self, message: QuestionMessage) -> None:
        prompt_parts = [message.title, message.content]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        request = LLMRequest(
            message_id=message.message_id,
            trace_id=message.trace_id,
            question_id=message.question_id,
            title=message.title,
            content=message.content,
            prompt=prompt,
            best_answer=message.best_answer,
            attempts=message.attempts + 1,
        )
        self.producer.send(self.llm_topic, key=request.message_id, value=request.asdict())
        self.producer.flush()

    def process(self) -> None:
        LOGGER.info("Cache service iniciado")
        while True:
            records = self.consumer.poll(timeout_ms=1000)
            for _, messages in records.items():
                for record in messages:
                    payload = record.value
                    if record.topic == self.regen_topic:
                        LOGGER.info(
                            "Reintento solicitado",
                            extra={"question_id": payload.get("question_id"), "attempts": payload.get("attempts")},
                        )
                        attempts = int(payload.get("attempts", 0))
                        request = LLMRequest(
                            message_id=payload["message_id"],
                            trace_id=payload["trace_id"],
                            question_id=payload["question_id"],
                            title=payload.get("title", ""),
                            content=payload.get("content", ""),
                            prompt=payload.get("prompt", ""),
                            best_answer=payload.get("best_answer", ""),
                            attempts=attempts + 1,
                        )
                        self.producer.send(self.llm_topic, key=request.message_id, value=request.asdict())
                        self.producer.flush()
                        continue

                    message = QuestionMessage(**payload)
                    cached = self.cache.get(message.question_id)
                    if cached:
                        LOGGER.info("Hit de caché", extra={"question_id": message.question_id})
                        self._emit_validated(message, cached, source="cache")
                    else:
                        storage_hit = self._lookup_storage(message.question_id)
                        if storage_hit:
                            LOGGER.info(
                                "Respuesta encontrada en almacenamiento",
                                extra={"question_id": message.question_id},
                            )
                            self.cache.put(message.question_id, storage_hit)
                            self._emit_validated(message, storage_hit, source="storage")
                        else:
                            LOGGER.info(
                                "Cache miss", extra={"question_id": message.question_id}
                            )
                            self._emit_llm_request(message)
                if messages:
                    self.consumer.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servicio de caché productor/consumidor")
    parser.add_argument("--policy", default="lru", choices=["lru", "lfu", "fifo"])
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--ttl", type=float, default=3600)
    parser.add_argument("--mongo-uri", default="mongodb://mongo:27017/")
    parser.add_argument("--mongo-db", default="yahoo_db")
    parser.add_argument("--mongo-coll", default="results")
    parser.add_argument("--input-topic", default="questions_in")
    parser.add_argument("--llm-topic", default="llm_requests")
    parser.add_argument("--validated-topic", default="validated_responses")
    parser.add_argument("--regeneration-topic", default="regeneration_requests")
    parser.add_argument("--group-id", default="cache-service")
    args = parser.parse_args()
    configure_logging()
    service = CacheService(
        policy=args.policy,
        size=args.size,
        ttl=args.ttl,
        mongo_uri=args.mongo_uri,
        database=args.mongo_db,
        collection=args.mongo_coll,
        input_topic=args.input_topic,
        llm_topic=args.llm_topic,
        validated_topic=args.validated_topic,
        regeneration_topic=args.regeneration_topic,
        group_id=args.group_id,
    )
    service.process()


if __name__ == "__main__":  # pragma: no cover - punto de entrada
    main()
