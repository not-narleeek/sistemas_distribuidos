from __future__ import annotations

import argparse
import csv
import json
import os
import random
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import matplotlib
import pandas as pd
from pymongo import MongoClient

matplotlib.use("Agg")
import matplotlib.pyplot as plt

def poisson_interarrival(lmbda: float) -> float:
    """Tiempo de espera entre llegadas para un proceso de Poisson."""

def poisson_interarrival(lmbda: float) -> float:
    """Tiempo de espera entre llegadas para un proceso de Poisson."""

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


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_fragment(value: object) -> str:
    return str(value).replace(" ", "-").replace("/", "-").replace(".", "_")


def build_log_filename(
    dist: str,
    total_queries: int,
    params: dict[str, float],
    output_dir: Path,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")

    fragments: list[str] = ["traffic", dist, f"n{total_queries}"]
    if dist == "poisson":
        fragments.append(f"lambda{sanitize_fragment(params['lmbda'])}")
    else:
        fragments.append(f"low{sanitize_fragment(params['low'])}")
        fragments.append(f"high{sanitize_fragment(params['high'])}")

    cache_policy = os.getenv("CACHE_POLICY")
    cache_size = os.getenv("CACHE_SIZE")
    cache_ttl = os.getenv("CACHE_TTL")

    if cache_policy:
        fragments.append(f"cache{sanitize_fragment(cache_policy)}")
    if cache_size:
        fragments.append(f"size{sanitize_fragment(cache_size)}")
    if cache_ttl:
        fragments.append(f"ttl{sanitize_fragment(cache_ttl)}")

    fragments.append(timestamp)

    ensure_directory(output_dir)
    return output_dir / ("_".join(fragments) + ".csv")


def write_rows(log_file: Path, rows: Iterable[Iterable[object]]) -> None:
    write_header = not log_file.exists()
    with log_file.open(mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if write_header:
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
        for row in rows:
            writer.writerow(row)


def generate_graphs(log_file: Path, output_dir: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return

    df = pd.DataFrame(rows)
    if df.empty:
        return

    df["latency"] = pd.to_numeric(df["latency"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    plots_dir = ensure_directory(output_dir / "plots")
    base_name = log_file.stem

    status_counts = df["status"].value_counts().sort_index()
    if not status_counts.empty:
        palette = {
            "HIT": "#4caf50",
            "MISS": "#f44336",
            "ERROR": "#ff9800",
            "UNKNOWN": "#9e9e9e",
        }
        colors = [palette.get(status, "#2196f3") for status in status_counts.index]
        plt.figure(figsize=(8, 4))
        status_counts.plot(kind="bar", color=colors)
        plt.title("Distribución de estados de caché")
        plt.xlabel("Estado")
        plt.ylabel("Cantidad de consultas")
        plt.tight_layout()
        plt.savefig(plots_dir / f"{base_name}_status.png", dpi=150)
        plt.close()

    if df["latency"].notna().any():
        plt.figure(figsize=(10, 4))
        plt.plot(range(1, len(df) + 1), df["latency"], marker="o", linewidth=1)
        plt.title("Latencia por consulta")
        plt.xlabel("Consulta")
        plt.ylabel("Latencia (s)")
        plt.grid(True, linestyle="--", alpha=0.4)
        plt.tight_layout()
        plt.savefig(plots_dir / f"{base_name}_latency.png", dpi=150)
        plt.close()

    if df["score"].notna().any():
        plt.figure(figsize=(10, 4))
        plt.plot(range(1, len(df) + 1), df["score"], marker="o", color="#1f77b4", linewidth=1)
        plt.title("Evolución del puntaje de calidad")
        plt.xlabel("Consulta")
        plt.ylabel("Score (0-1)")
        plt.grid(True, linestyle="--", alpha=0.4)
        plt.ylim(0, 1)
        plt.tight_layout()
        plt.savefig(plots_dir / f"{base_name}_score.png", dpi=150)
        plt.close()


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
    log_file: Path | None = None,
    output_dir: Path | None = None,
):
    dataset_csv = Path(dataset_csv) if dataset_csv else None

    questions = load_questions_from_csv(dataset_csv) if dataset_csv else []
    if not questions:
        questions = load_questions_from_mongo(mongo_uri, db_name, coll_name)

    if not questions:
        raise RuntimeError("No se encontraron preguntas disponibles para generar tráfico")

    if log_file is None:
        target_dir = output_dir or Path.cwd()
        log_file = target_dir / "traffic_log.csv"

    print(
        f"[Generator] {len(questions)} preguntas cargadas. "
        f"Generando {total_queries} consultas usando '{dist}'."
    )
    print(f"[Generator] Registrando métricas en {log_file}")

    run_rows: list[list[object]] = []
    chart_rows: list[dict[str, object]] = []

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
        row = [
            timestamp,
            "GET",
            payload["id"],
            payload["title"][:50],
            status,
            round(latency, 4),
            score,
        ]
        run_rows.append(row)
        chart_rows.append(
            {
                "timestamp": timestamp,
                "status": status,
                "latency": round(latency, 4),
                "score": score,
            }
        )

    print("[Generator] Finalizado.")
    write_rows(log_file, run_rows)
    if output_dir:
        generate_graphs(log_file, output_dir, chart_rows)
    else:
        generate_graphs(log_file, log_file.parent, chart_rows)

    print("[Generator] Finalizado.")
    write_rows(log_file, run_rows)
    if output_dir:
        generate_graphs(log_file, output_dir, chart_rows)
    else:
        generate_graphs(log_file, log_file.parent, chart_rows)

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
        "--output_dir",
        type=str,
        default="",
        help="Directorio donde se almacenarán los CSV y gráficas generadas",
    )

    args = parser.parse_args()
    params = {"lmbda": args.lmbda, "low": args.low, "high": args.high}
    output_dir = Path(args.output_dir) if args.output_dir else None
    if not output_dir and os.getenv("GENERATOR_OUTPUT_DIR"):
        output_dir = Path(os.getenv("GENERATOR_OUTPUT_DIR"))

    if output_dir:
        ensure_directory(output_dir)

    print(f"[Generador] Iniciando en modo continuo ({args.dist})...")
    while True:
        log_file = build_log_filename(args.dist, args.n, params, output_dir or Path.cwd())
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
            log_file=log_file,
            output_dir=output_dir or log_file.parent,
        )
