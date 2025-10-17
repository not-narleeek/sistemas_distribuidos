from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from datetime import datetime

from pymongo import MongoClient, UpdateOne


def to_datetime_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class StorageHandler:
    def __init__(self, mongo_uri: str, database: str, collection: str, metrics_collection: str):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")
        self.collection = self.client[database][collection]
        self.metrics = self.client[database][metrics_collection]

    def store_result(self, payload: dict) -> dict:
        required_fields = {"id_pregunta", "pregunta", "respuesta_dataset", "respuesta_llm", "score"}
        if not required_fields.issubset(payload):
            return {"status": "error", "reason": "missing_fields"}

        now = to_datetime_iso()
        query = {"id_pregunta": payload["id_pregunta"]}
        update = {
            "$set": {
                "pregunta": payload["pregunta"],
                "respuesta_dataset": payload["respuesta_dataset"],
                "respuesta_llm": payload["respuesta_llm"],
                "score": payload["score"],
                "aceptado": payload.get("aceptado", False),
                "ultima_actualizacion": now,
            },
            "$inc": {"contador_consultas": 1},
            "$setOnInsert": {"creado_en": now},
        }
        self.collection.update_one(query, update, upsert=True)
        return {"status": "ok"}

    def increment_hit(self, question_id: str) -> dict:
        if not question_id:
            return {"status": "error", "reason": "missing_id"}
        update = {
            "$inc": {"contador_consultas": 1},
            "$set": {"ultima_actualizacion": to_datetime_iso()},
        }
        self.collection.update_one({"id_pregunta": question_id}, update, upsert=True)
        return {"status": "ok"}

    def record_metrics(self, payload: dict) -> dict:
        inc_payload = {
            "total": 1,
            "hits": 1 if payload.get("hit") else 0,
            "misses": 0 if payload.get("hit") else 1,
            "latency_acum": payload.get("latency", 0.0),
            "score_acum": payload.get("score", 0.0),
        }

        update_ops = [
            UpdateOne(
                {"_id": "global"},
                {
                    "$inc": inc_payload,
                    "$set": {
                        "last_score": payload.get("score"),
                        "last_latency": payload.get("latency"),
                        "updated_at": to_datetime_iso(),
                    },
                    "$setOnInsert": {"created_at": to_datetime_iso()},
                },
                upsert=True,
            )
        ]
        self.metrics.bulk_write(update_ops)
        return {"status": "ok"}


def handle_message(handler: StorageHandler, message: str) -> dict:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return {"status": "error", "reason": "invalid_json"}

    action = payload.get("action")
    data = payload.get("data", {})

    if action == "store_result":
        return handler.store_result(data)
    if action == "increment_hit":
        return handler.increment_hit(data.get("id_pregunta"))
    if action == "record_metrics":
        return handler.record_metrics(data)

    return {"status": "error", "reason": "unknown_action"}


def run_storage_service(host: str, port: int, handler: StorageHandler):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"[Storage] Servicio escuchando en {host}:{port}")

    def handle_client(conn: socket.socket):
        with conn:
            try:
                data = conn.recv(16384).decode().strip()
            except socket.error:
                conn.sendall(json.dumps({"status": "error", "reason": "socket_error"}).encode())
                return

            if not data:
                return

            response = handle_message(handler, data)
            conn.sendall(json.dumps(response).encode() + b"\n")

    while True:
        client, _ = server.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Storage microservice")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7100)
    parser.add_argument("--mongo", default="mongodb://mongo:27017/")
    parser.add_argument("--db", default="yahoo_db")
    parser.add_argument("--coll", default="results")
    parser.add_argument("--metrics", default="metrics")

    args = parser.parse_args()
    storage_handler = None
    for attempt in range(30):
        try:
            storage_handler = StorageHandler(args.mongo, args.db, args.coll, args.metrics)
            break
        except Exception as exc:
            wait_time = 2
            print(f"[Storage] Esperando a MongoDB ({exc})... reintento {attempt + 1}")
            time.sleep(wait_time)

    if not storage_handler:
        raise RuntimeError("No se pudo conectar a MongoDB para almacenamiento")

    run_storage_service(args.host, args.port, storage_handler)
