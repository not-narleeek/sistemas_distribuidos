from __future__ import annotations

import json
import os
from dataclasses import dataclass

from pyflink.common import WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream import (
    KeyedProcessFunction,
    OutputTag,
    RuntimeContext,
    StreamExecutionEnvironment,
)
from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer, FlinkKafkaProducer
from pyflink.datastream.state import ValueState, ValueStateDescriptor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from common import ValidatedResponse


@dataclass
class ScoreConfig:
    threshold: float = 0.6
    max_attempts: int = 3


class ScoreProcess(KeyedProcessFunction):
    def __init__(self, cfg: ScoreConfig, regeneration_tag: OutputTag):
        super().__init__()
        self.cfg = cfg
        self.regeneration_tag = regeneration_tag
        self.state: ValueState | None = None
        self.accepted_counter = None
        self.regenerated_counter = None

    def open(self, runtime_context: RuntimeContext):  # pragma: no cover - inicializa en Flink
        descriptor = ValueStateDescriptor("attempts", Types.INT())
        self.state = runtime_context.get_state(descriptor)
        metric_group = runtime_context.get_metric_group()
        self.accepted_counter = metric_group.counter("responses_accepted")
        self.regenerated_counter = metric_group.counter("responses_regenerated")

    def process_element(self, value, ctx):  # pragma: no cover - ejecutado por Flink
        message = json.loads(value)
        attempts = self.state.value() or 0
        attempts += 1
        self.state.update(attempts)

        best_answer = message.get("best_answer", "")
        llm_answer = message.get("llm_answer", "")
        score = float(compute_cosine_score(best_answer, llm_answer))
        accepted = score >= self.cfg.threshold or attempts >= self.cfg.max_attempts

        validated = ValidatedResponse(
            message_id=message["message_id"],
            trace_id=message["trace_id"],
            question_id=message["question_id"],
            title=message.get("title", ""),
            content=message.get("prompt", ""),
            llm_answer=llm_answer,
            best_answer=best_answer,
            score=score,
            accepted=accepted,
            source="flink",
            attempts=attempts,
        )

        if accepted:
            self.accepted_counter.inc()
            self.state.clear()
            yield json.dumps(validated.asdict())
        else:
            self.regenerated_counter.inc()
            regen_payload = {
                "message_id": message["message_id"],
                "trace_id": message["trace_id"],
                "question_id": message["question_id"],
                "title": message.get("title", ""),
                "content": message.get("content", ""),
                "prompt": message.get("prompt", ""),
                "best_answer": best_answer,
                "attempts": attempts,
            }
            ctx.output(self.regeneration_tag, json.dumps(regen_payload))


def compute_cosine_score(expected: str, actual: str) -> float:
    if not expected or not actual:
        return 0.0
    vectorizer = TfidfVectorizer().fit([expected, actual])
    vectors = vectorizer.transform([expected, actual])
    score = cosine_similarity(vectors[0], vectors[1])[0][0]
    return max(0.0, min(1.0, float(score)))


def build_consumer(topic: str) -> FlinkKafkaConsumer:
    properties = {
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "group.id": os.getenv("FLINK_GROUP_ID", "flink-job"),
        "auto.offset.reset": "earliest",
    }
    return FlinkKafkaConsumer(topic, SimpleStringSchema(), properties)


def build_producer(topic: str) -> FlinkKafkaProducer:
    properties = {"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")}
    # Flink 1.17 removed the exposed flush-on-checkpoint toggle from the Python
    # wrapper, but the producer keeps it enabled by default, preserving the
    # original at-least-once guarantees without additional configuration.
    return FlinkKafkaProducer(
        topic,
        SimpleStringSchema(),
        properties,
    )


def main():  # pragma: no cover - ejecutado en cluster
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(int(os.getenv("FLINK_PARALLELISM", "1")))
    cfg = ScoreConfig(
        threshold=float(os.getenv("SCORE_THRESHOLD", "0.6")),
        max_attempts=int(os.getenv("MAX_RETRIES", "3")),
    )

    consumer = build_consumer(os.getenv("LLM_RESPONSES_TOPIC", "llm_responses"))
    stream = env.add_source(consumer).name("llm-responses-source")

    regeneration_tag = OutputTag("regeneration", Types.STRING())
    processed = (
        stream.assign_timestamps_and_watermarks(WatermarkStrategy.for_monotonous_timestamps())
        .key_by(lambda raw: json.loads(raw)["message_id"], key_type=Types.STRING())
        .process(ScoreProcess(cfg, regeneration_tag))
    )

    validated_sink = build_producer(os.getenv("VALIDATED_TOPIC", "validated_responses"))
    processed.add_sink(validated_sink).name("validated-sink")

    regeneration_stream = processed.get_side_output(regeneration_tag)
    regeneration_sink = build_producer(os.getenv("REGEN_TOPIC", "regeneration_requests"))
    regeneration_stream.add_sink(regeneration_sink).name("regeneration-sink")

    env.execute("flink-streaming-score")


if __name__ == "__main__":
    main()
