from __future__ import annotations
import argparse
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from common import (
    ErrorMessage,
    LLMRequest,
    LLMResponse,
    build_consumer,
    build_producer,
    configure_logging,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RetryConfig:
    max_retries: int = 5
    base_delay: float = 1.0
    jitter: float = 0.5


class LocalLLM:
    def __init__(self, latency_ms: float = 250.0):
        self.latency_ms = latency_ms

    def generate(self, prompt: str) -> str:
        time.sleep(self.latency_ms / 1000.0)
        summary = " ".join(prompt.split()[:60])
        return (
            "Respuesta generada automáticamente en modo offline. "
            "Resumen de la pregunta: "
            f"{summary}."
        )


class LLMWorker:
    def __init__(
        self,
        *,
        request_topic: str,
        response_topic: str,
        error_topic: str,
        group_id: str,
        retry_config: RetryConfig,
        llm: Optional[LocalLLM] = None,
    ):
        self.consumer = build_consumer(request_topic, group_id=group_id)
        self.producer = build_producer()
        self.response_topic = response_topic
        self.error_topic = error_topic
        self.retry_config = retry_config
        self.llm = llm or LocalLLM()

    def _emit_response(self, request: LLMRequest, answer: str, latency_ms: float) -> None:
        response = LLMResponse(
            message_id=request.message_id,
            trace_id=request.trace_id,
            question_id=request.question_id,
            title=request.title,
            content=request.content,
            prompt=request.prompt,
            llm_answer=answer,
            best_answer=request.best_answer,
            latency_ms=latency_ms,
            attempts=request.attempts,
        )
        self.producer.send(self.response_topic, key=response.message_id, value=response.asdict())
        self.producer.flush()

    def _emit_error(self, request: LLMRequest, exc: Exception, attempt: int) -> None:
        backoff = self.retry_config.base_delay * (2 ** (attempt - 1))
        backoff += random.uniform(0, self.retry_config.jitter)
        retry_at = time.time() + backoff
        error = ErrorMessage(
            message_id=request.message_id,
            trace_id=request.trace_id,
            question_id=request.question_id,
            error_type=exc.__class__.__name__,
            error_detail=str(exc),
            attempts=attempt,
            retry_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(retry_at)),
        )
        self.producer.send(self.error_topic, key=error.message_id, value=error.asdict())
        self.producer.flush()

    def process(self) -> None:
        LOGGER.info("LLM worker escuchando solicitudes")
        while True:
            records = self.consumer.poll(timeout_ms=1000)
            for _, messages in records.items():
                for record in messages:
                    payload = record.value
                    request = LLMRequest(**payload)
                    start = time.time()
                    try:
                        answer = self.llm.generate(request.prompt)
                    except Exception as exc:  # pragma: no cover
                        LOGGER.exception("Fallo al generar respuesta", exc_info=exc)
                        self._emit_error(request, exc, request.attempts)
                    else:
                        latency_ms = (time.time() - start) * 1000
                        self._emit_response(request, answer, latency_ms)
                if messages:
                    self.consumer.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Consumidor LLM sobre Kafka")
    parser.add_argument("--request-topic", default="llm_requests")
    parser.add_argument("--response-topic", default="llm_responses")
    parser.add_argument("--error-topic", default="llm_errors")
    parser.add_argument("--group-id", default="llm-consumer")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--base-delay", type=float, default=1.0)
    parser.add_argument("--jitter", type=float, default=0.5)
    parser.add_argument("--latency", type=float, default=250.0)
    args = parser.parse_args()
    configure_logging()
    worker = LLMWorker(
        request_topic=args.request_topic,
        response_topic=args.response_topic,
        error_topic=args.error_topic,
        group_id=args.group_id,
        retry_config=RetryConfig(
            max_retries=args.max_retries,
            base_delay=args.base_delay,
            jitter=args.jitter,
        ),
        llm=LocalLLM(latency_ms=args.latency),
    )
    worker.process()


if __name__ == "__main__":  # pragma: no cover
    main()
