from __future__ import annotations

import argparse
import logging

from pymongo import UpdateOne

from common import ValidatedResponse, build_consumer, configure_logging, connect_mongo

LOGGER = logging.getLogger(__name__)


class StorageService:
    def __init__(
        self,
        *,
        mongo_uri: str,
        database: str,
        collection: str,
        metrics_collection: str,
        topic: str,
        group_id: str,
    ):
        self.client = connect_mongo(mongo_uri)
        self.collection = self.client[database][collection]
        self.metrics = self.client[database][metrics_collection]
        self.consumer = build_consumer(topic, group_id=group_id)

    def _store_validated(self, response: ValidatedResponse) -> None:
        payload = {
            "id_pregunta": response.question_id,
            "pregunta": response.title,
            "contenido": response.content,
            "respuesta_dataset": response.best_answer,
            "respuesta_llm": response.llm_answer,
            "score": response.score,
            "aceptado": response.accepted,
            "ultima_actualizacion": response.decided_at,
        }
        query = {"id_pregunta": response.question_id}
        update = {
            "$set": payload,
            "$inc": {"contador_consultas": 1},
            "$setOnInsert": {"creado_en": response.decided_at},
        }
        self.collection.update_one(query, update, upsert=True)

    def _record_metrics(self, response: ValidatedResponse) -> None:
        update = UpdateOne(
            {"_id": "global"},
            {
                "$inc": {
                    "procesadas": 1,
                    "aceptadas": 1 if response.accepted else 0,
                    "rechazadas": 0 if response.accepted else 1,
                    "score_acum": float(response.score),
                },
                "$set": {
                    "ultimo_score": float(response.score),
                    "actualizado_en": response.decided_at,
                },
                "$setOnInsert": {"creado_en": response.decided_at},
            },
            upsert=True,
        )
        self.metrics.bulk_write([update])

    def process(self) -> None:
        LOGGER.info("Storage service escuchando mensajes validados")
        while True:
            records = self.consumer.poll(timeout_ms=1000)
            for _, messages in records.items():
                for record in messages:
                    value = record.value
                    response = ValidatedResponse(**value)
                    self._store_validated(response)
                    self._record_metrics(response)
                    LOGGER.info(
                        "Respuesta persistida",
                        extra={
                            "question_id": response.question_id,
                            "score": response.score,
                            "accepted": response.accepted,
                        },
                    )
                if messages:
                    self.consumer.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servicio de almacenamiento para respuestas validadas")
    parser.add_argument("--mongo-uri", default="mongodb://mongo:27017/")
    parser.add_argument("--db", default="yahoo_db")
    parser.add_argument("--collection", default="results")
    parser.add_argument("--metrics", default="metrics")
    parser.add_argument("--topic", default="validated_responses")
    parser.add_argument("--group-id", default="storage-service")
    args = parser.parse_args()
    configure_logging()
    service = StorageService(
        mongo_uri=args.mongo_uri,
        database=args.db,
        collection=args.collection,
        metrics_collection=args.metrics,
        topic=args.topic,
        group_id=args.group_id,
    )
    service.process()


if __name__ == "__main__":  # pragma: no cover
    main()
