from __future__ import annotations

import argparse
import csv
import os
import random
import time
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd
from kafka.admin import NewTopic
from pymongo import MongoClient

from common import QuestionMessage, build_producer, ensure_topics, configure_logging

matplotlib.use("Agg")


def poisson_interarrival(lmbda: float) -> float:
    return random.expovariate(lmbda)


def uniform_interarrival(low: float, high: float) -> float:
    return random.uniform(low, high)


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_fragment(value: object) -> str:
    return str(value).replace(" ", "-").replace("/", "-").replace(".", "_")


def build_log_filename(dist: str, total_queries: int, params: dict[str, float], output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    fragments: list[str] = ["traffic", dist, f"n{total_queries}"]
    if dist == "poisson":
        fragments.append(f"lambda{sanitize_fragment(params['lmbda'])}")
    else:
        fragments.append(f"low{sanitize_fragment(params['low'])}")
        fragments.append(f"high{sanitize_fragment(params['high'])}")
    fragments.append(timestamp)
    ensure_directory(output_dir)
    return output_dir / ("_".join(fragments) + ".csv")


def write_rows(log_file: Path, rows: list[list[object]]) -> None:
    write_header = not log_file.exists()
    with log_file.open(mode="a", newline="", encoding="utf-8") as handler:
        writer = csv.writer(handler)
        if write_header:
            writer.writerow([
                "timestamp",
                "operation",
                "message_id",
                "question_id",
                "status",
                "latency",
                "topic",
            ])
        writer.writerows(rows)


def generate_graphs(log_file: Path, output_dir: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    if df.empty:
        return
    plots_dir = ensure_directory(output_dir / "plots")
    base_name = log_file.stem
    status_counts = df["status"].value_counts().sort_index()
    if not status_counts.empty:
        ax = status_counts.plot(kind="bar", color="#4caf50", title="Mensajes publicados")
        ax.set_xlabel("Estado")
        ax.set_ylabel("Cantidad")
        fig = ax.get_figure()
        fig.tight_layout()
        fig.savefig(plots_dir / f"{base_name}_status.png", dpi=150)
        fig.clf()


def load_questions_from_csv(csv_path: Path) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
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


def load_questions_from_mongo(mongo_uri: str, db_name: str, coll_name: str) -> list[dict[str, object]]:
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


def run_generator(
    dist: str,
    params: dict[str, float],
    total_queries: int,
    mongo_uri: str,
    db_name: str,
    coll_name: str,
    dataset_csv: Path | None,
    output_dir: Path,
    topic: str,
    partitions: int,
    replication_factor: int,
) -> None:
    questions = load_questions_from_csv(dataset_csv) if dataset_csv else []
    if not questions:
        questions = load_questions_from_mongo(mongo_uri, db_name, coll_name)
    if not questions:
        raise RuntimeError("No se encontraron preguntas disponibles para generar tráfico")
    producer = build_producer()
    ensure_topics([
        NewTopic(name=topic, num_partitions=partitions, replication_factor=replication_factor)
    ])
    log_file = build_log_filename(dist, total_queries, params, output_dir)
    rows: list[list[object]] = []
    graph_rows: list[dict[str, object]] = []
    for i in range(1, total_queries + 1):
        wait = (
            poisson_interarrival(params["lmbda"])
            if dist == "poisson"
            else uniform_interarrival(params["low"], params["high"])
        )
        time.sleep(wait)
        doc = random.choice(questions)
        message = QuestionMessage(
            question_id=str(doc.get("_id")),
            title=doc.get("question_title", ""),
            content=doc.get("question_content", ""),
            best_answer=doc.get("best_answer", ""),
        )
        producer.send(topic, key=message.message_id, value=message.asdict())
        producer.flush()
        timestamp = datetime.utcnow().isoformat()
        rows.append([
            timestamp,
            "PUBLISH",
            message.message_id,
            message.question_id,
            "ENQUEUED",
            wait,
            topic,
        ])
        graph_rows.append({"timestamp": timestamp, "status": "ENQUEUED"})
    write_rows(log_file, rows)
    generate_graphs(log_file, output_dir, graph_rows)
    print(f"[Generator] Publicadas {len(rows)} preguntas en {topic}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de tráfico hacia Kafka")
    parser.add_argument("--total", type=int, default=100, help="Total de preguntas a emitir")
    parser.add_argument("--distribution", choices=["poisson", "uniform"], default="poisson")
    parser.add_argument("--lambda", dest="lmbda", type=float, default=1.5)
    parser.add_argument("--low", type=float, default=0.1)
    parser.add_argument("--high", type=float, default=0.5)
    parser.add_argument("--mongo-uri", default="mongodb://mongo:27017/")
    parser.add_argument("--mongo-db", default="yahoo_db")
    parser.add_argument("--mongo-coll", default="preguntas")
    parser.add_argument("--dataset-csv", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/data/traffic"))
    parser.add_argument("--topic", default="questions_in")
    parser.add_argument("--partitions", type=int, default=3)
    parser.add_argument("--replication-factor", type=int, default=1)

    args = parser.parse_args()
    configure_logging()
    params = {"lmbda": args.lmbda, "low": args.low, "high": args.high}
    run_generator(
        dist=args.distribution,
        params=params,
        total_queries=args.total,
        mongo_uri=args.mongo_uri,
        db_name=args.mongo_db,
        coll_name=args.mongo_coll,
        dataset_csv=args.dataset_csv,
        output_dir=args.output,
        topic=args.topic,
        partitions=args.partitions,
        replication_factor=args.replication_factor,
    )
