from __future__ import annotations

import argparse
import csv
import json
import random
import socket
import time
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient


def poisson_interarrival(lmbda: float) -> float:
    """Tiempo de espera entre llegadas para un proceso de Poisson."""

    return random.expovariate(lmbda)


def uniform_interarrival(low: float, high: float) -> float:
    """Tiempo de espera uniforme entre dos límites."""

    return random.uniform(low, high)


def query_system(payload, host: str = "mongo", port: int = 5000) -> str:
    """Envia la consulta serializada al servicio de caché."""

    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode())
            response = sock.recv(16384).decode().strip()
            return response
    except Exception as exc:  # pragma: no cover - se reporta en logs
        return f"ERROR {exc}"


def log_to_csv(filepath: Path, row) -> None:
    """Append de una fila de métricas al archivo de tráfico."""

    with filepath.open(mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(row)


def load_questions_from_csv(csv_path: Path):
    """Carga preguntas desde un dataset CSV con columnas estándar."""

    questions = []
    if not csv_path.exists():
        return questions

    with csv_path.open(encoding="utf-8") as handler:
        reader = csv.DictReader(handler)
        for row in reader:
            qid = row.get("id") or row.get("_id")
            if not qid:
                continue
            questions.append(
                {
                    "_id": qid,
                    "question_title": row.get("question_title", ""),
                    "question_content": row.get("question_content", ""),
                    "best_answer": row.get("best_answer", ""),
                }
            )
    return questions


def load_questions_from_mongo(mongo_uri: str, db_name: str, coll_name: str):
    """Extrae preguntas desde MongoDB cuando no hay dataset local."""

    client = MongoClient(mongo_uri)
    collection = client[db_name][coll_name]
    return list(
        collection.find(
            {},
            {
                "question_title": 1,
                "question_content": 1,
                "best_answer": 1,
            },
        )
    )


def parse_response(raw_response: str):
    status = "UNKNOWN"
    payload = {}

    if raw_response.startswith("HIT"):
        status = "HIT"
    elif raw_response.startswith("MISS"):
        status = "MISS"
    elif raw_response.startswith("ERROR"):
        status = "ERROR"

    if "\n" in raw_response:
        try:
            payload = json.loads(raw_response.split("\n", 1)[1])
        except json.JSONDecodeError:
            payload = {}
    return status, payload


def run_generator(
    dist,
    params,
    total_queries,
    mongo_uri,
    db_name,
    coll_name,
    cache_host,
    cache_port,
    dataset_csv=None,
    log_path: Path | None = None,
):
    dataset_csv = Path(dataset_csv) if dataset_csv else None

    questions = load_questions_from_csv(dataset_csv) if dataset_csv else []
    if not questions:
        questions = load_questions_from_mongo(mongo_uri, db_name, coll_name)

    if not questions:
        raise RuntimeError("No se encontraron preguntas disponibles para generar tráfico")

    log_file = log_path or Path("traffic_log.csv")
    with log_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "timestamp",
                "operation",
                "id",
                "title",
                "status",
                "latency",
                "score",
            ]
        )

    print(
        f"[Generator] {len(questions)} preguntas cargadas. "
        f"Generando {total_queries} consultas usando '{dist}'."
    )

    for i in range(1, total_queries + 1):
        wait = (
            poisson_interarrival(params["lmbda"])
            if dist == "poisson"
            else uniform_interarrival(params["low"], params["high"])
        )
        time.sleep(wait)

        doc = random.choice(questions)
        payload = {
            "id": str(doc.get("_id")),
            "title": doc.get("question_title", ""),
            "content": doc.get("question_content", ""),
        }

        start = time.time()
        response = query_system(payload, host=cache_host, port=cache_port)
        latency = time.time() - start
        timestamp = datetime.now().isoformat(timespec="seconds")

        status, payload_response = parse_response(response)
        score = payload_response.get("score", "") if isinstance(payload_response, dict) else ""

        print(
            f"[{i:04d}] GET {payload['id']} → {status} · {latency:.3f}s · Score={score}"
        )
        log_to_csv(
            log_file,
            [
                timestamp,
                "GET",
                payload["id"],
                payload["title"][:50],
                status,
                round(latency, 4),
                score,
            ],
        )

    print("[Generator] Finalizado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generador de tráfico sintético para Yahoo Answers"
    )
    parser.add_argument("--dist", choices=["poisson", "uniform"], required=True)
    parser.add_argument("--lmbda", type=float, default=1.0)
    parser.add_argument("--low", type=float, default=0.5)
    parser.add_argument("--high", type=float, default=2.0)
    parser.add_argument("--n", type=int, default=8000)
    parser.add_argument("--mongo", type=str, default="mongodb://mongo:27017/")
    parser.add_argument("--db", type=str, default="yahoo_db")
    parser.add_argument("--coll", type=str, default="questions")
    parser.add_argument("--cache_host", type=str, default="localhost")
    parser.add_argument("--cache_port", type=int, default=5000)
    parser.add_argument(
        "--dataset_csv",
        type=str,
        default="",
        help="Ruta opcional a train.csv o test.csv con preguntas de Yahoo! Answers",
    )
    parser.add_argument(
        "--log_path",
        type=str,
        default="",
        help="Ruta del archivo CSV donde se almacenarán las métricas de tráfico",
    )

    args = parser.parse_args()
    params = {"lmbda": args.lmbda, "low": args.low, "high": args.high}
    log_file = Path(args.log_path) if args.log_path else None

    print(f"[Generador] Iniciando en modo continuo ({args.dist})...")
    while True:
        run_generator(
            args.dist,
            params,
            args.n,
            args.mongo,
            args.db,
            args.coll,
            args.cache_host,
            args.cache_port,
            dataset_csv=args.dataset_csv,
            log_path=log_file,
        )
