from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class ScoreRequest:
    question_id: str
    best_answer: str
    llm_answer: str


def cosine_score(best_answer: str, llm_answer: str) -> float:
    if not best_answer or not llm_answer:
        return 0.0

    vectorizer = TfidfVectorizer().fit([best_answer, llm_answer])
    vectors = vectorizer.transform([best_answer, llm_answer])
    score = cosine_similarity(vectors[0], vectors[1])[0][0]
    return max(0.0, min(1.0, float(score)))


def evaluate(request: ScoreRequest, acceptance_threshold: float) -> dict[str, object]:
    score = cosine_score(request.best_answer, request.llm_answer)
    accepted = score >= acceptance_threshold
    return {"score": round(score, 4), "accepted": accepted}


def parse_request(raw: str) -> ScoreRequest | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None

    try:
        return ScoreRequest(
            question_id=str(payload["question_id"]),
            best_answer=payload.get("best_answer", ""),
            llm_answer=payload.get("llm_answer", ""),
        )
    except KeyError:
        return None


def run_score_service(host: str, port: int, threshold: float):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(
        f"[Score] Servicio escuchando en {host}:{port} con umbral de aceptación {threshold}"
    )

    def handle_connection(conn: socket.socket):
        with conn:
            try:
                data = conn.recv(8192).decode().strip()
            except socket.error:
                return

            if not data:
                return

            request = parse_request(data)
            if not request:
                conn.sendall(json.dumps({"error": "invalid_payload"}).encode() + b"\n")
                return

            started = time.time()
            result = evaluate(request, threshold)
            result["elapsed_ms"] = round((time.time() - started) * 1000, 2)
            conn.sendall(json.dumps(result).encode() + b"\n")

    while True:
        client, _ = server.accept()
        threading.Thread(target=handle_connection, args=(client,), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score service for LLM responses")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7000)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Umbral mínimo para considerar aceptada una respuesta",
    )

    args = parser.parse_args()
    run_score_service(args.host, args.port, args.threshold)
