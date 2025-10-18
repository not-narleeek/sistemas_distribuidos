from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from pymongo import MongoClient


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
        self.request_count = 0
        self.total_latency = 0.0

    # Métodos que las políticas deben implementar
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

    def record_latency(self, latency: float) -> None:
        self.total_latency += latency
        self.request_count += 1

    def stats(self) -> dict[str, float]:
        hit_rate = self.hits / self.request_count if self.request_count else 0.0
        miss_rate = self.misses / self.request_count if self.request_count else 0.0
        avg_latency = self.total_latency / self.request_count if self.request_count else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(hit_rate, 4),
            "miss_rate": round(miss_rate, 4),
            "avg_latency": round(avg_latency, 4),
        }


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


class ServiceClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        retries: int = 3,
        backoff: float = 0.5,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = json.dumps(payload) + "\n"
        for attempt in range(self.retries):
            try:
                with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendall(message.encode())
                    response = sock.recv(16384).decode().strip()
                    return json.loads(response) if response else {}
            except (socket.error, json.JSONDecodeError) as exc:
                wait_time = self.backoff * (attempt + 1)
                print(
                    f"[Cache] Error comunicando con {self.host}:{self.port} ({exc}). Reintentando en {wait_time:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(wait_time)
        raise ConnectionError(f"No se pudo contactar a {self.host}:{self.port}")


def wait_for_service(host: str, port: int, timeout: int = 60) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[Cache] Servicio {host}:{port} disponible")
                return True
        except (socket.error, ConnectionRefusedError):
            print(f"[Cache] Esperando a {host}:{port}...")
            time.sleep(2)
    return False


def build_cache(policy: str, size: int, ttl: float) -> CacheBase:
    if policy == "lru":
        return LRUCache(size, ttl)
    if policy == "lfu":
        return LFUCache(size, ttl)
    if policy == "fifo":
        return FIFOCache(size, ttl)
    raise ValueError(f"Política desconocida: {policy}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=["lru", "lfu", "fifo"], required=True)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--ttl", type=float, default=0.0, help="TTL en segundos para cada entrada de caché")
    parser.add_argument("--mongo", default="mongodb://mongo:27017/")
    parser.add_argument("--db", default="yahoo_db")
    parser.add_argument("--coll", default="questions")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--dummy_host", default="llm")
    parser.add_argument("--dummy_port", type=int, default=6000)
    parser.add_argument("--score_host", default="score")
    parser.add_argument("--score_port", type=int, default=7000)
    parser.add_argument("--storage_host", default="storage")
    parser.add_argument("--storage_port", type=int, default=7100)
    parser.add_argument(
        "--llm_timeout",
        type=float,
        default=15.0,
        help="Tiempo máximo de espera (s) para obtener respuesta del LLM",
    )
    parser.add_argument(
        "--llm_retries",
        type=int,
        default=3,
        help="Número de reintentos al contactar al LLM",
    )
    args = parser.parse_args()

    cache = build_cache(args.policy, args.size, args.ttl)

    mongo_host = args.mongo.split("//")[-1].split(":")[0]
    if not wait_for_service(mongo_host, 27017):
        print("[Cache] MongoDB no disponible", file=sys.stderr)
        sys.exit(1)

    if not wait_for_service(args.dummy_host, args.dummy_port):
        print("[Cache] Servicio LLM no disponible", file=sys.stderr)
        sys.exit(1)

    if not wait_for_service(args.score_host, args.score_port):
        print("[Cache] Servicio de scoring no disponible", file=sys.stderr)
        sys.exit(1)

    if not wait_for_service(args.storage_host, args.storage_port):
        print("[Cache] Servicio de almacenamiento no disponible", file=sys.stderr)
        sys.exit(1)

    try:
        client = MongoClient(args.mongo)
        client.admin.command("ping")
        collection = client[args.db][args.coll]
    except Exception as exc:
        print(f"[Cache] Error conectando a MongoDB: {exc}", file=sys.stderr)
        sys.exit(1)

    llm_client = ServiceClient(
        args.dummy_host,
        args.dummy_port,
        timeout=args.llm_timeout,
        retries=args.llm_retries,
    )
    score_client = ServiceClient(args.score_host, args.score_port)
    storage_client = ServiceClient(args.storage_host, args.storage_port)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("0.0.0.0", args.port))
        server.listen(5)
        print(
            f"[Cache] Servicio iniciado en 0.0.0.0:{args.port} con política {args.policy.upper()} y TTL={args.ttl}s"
        )
    except Exception as exc:
        print(f"[Cache] Error iniciando servidor: {exc}", file=sys.stderr)
        sys.exit(1)

    while True:
        conn, addr = server.accept()
        with conn:
            data = conn.recv(4096).decode().strip()
            if not data:
                continue

            if data.upper() == "STATS":
                conn.sendall(json.dumps(cache.stats()).encode() + b"\n")
                continue

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                conn.sendall(b"INVALID_JSON\n")
                continue

            key = payload.get("id")
            if not key:
                conn.sendall(b"MISSING_ID\n")
                continue

            start = time.time()
            cached = cache.get(key)
            if cached:
                latency = time.time() - start
                cache.record_latency(latency)
                response = {
                    "question_id": key,
                    "score": cached.get("score"),
                    "accepted": cached.get("accepted", False),
                    "source": "cache",
                }
                conn.sendall(
                    f"HIT {key} ({latency:.4f}s)\n{json.dumps(response)}\n".encode()
                )
                try:
                    storage_client.request(
                        {
                            "action": "increment_hit",
                            "data": {"id_pregunta": key},
                        }
                    )
                    storage_client.request(
                        {
                            "action": "record_metrics",
                            "data": {"hit": True, "latency": latency, "score": cached.get("score", 0.0)},
                        }
                    )
                except Exception as exc:
                    print(f"[Cache] No se pudo registrar hit: {exc}", file=sys.stderr)
                continue

            # Cache miss
            try:
                object_id = ObjectId(key)
            except Exception:
                conn.sendall(f"INVALID_ID {key}\n".encode())
                continue

            doc = collection.find_one({"_id": object_id})
            if not doc:
                conn.sendall(f"NOTFOUND {key}\n".encode())
                continue

            question_title = doc.get("question_title", "")
            question_content = doc.get("question_content", "")
            best_answer = doc.get("best_answer", "")

            try:
                llm_response = llm_client.request(
                    {
                        "id": key,
                        "title": question_title,
                        "content": question_content,
                    }
                )
            except Exception as exc:
                conn.sendall(f"ERROR LLM {exc}\n".encode())
                continue

            if "generated_answer" not in llm_response:
                conn.sendall(f"ERROR LLM_RESPONSE {llm_response}\n".encode())
                continue

            llm_answer = llm_response["generated_answer"]

            try:
                score_response = score_client.request(
                    {
                        "question_id": key,
                        "best_answer": best_answer,
                        "llm_answer": llm_answer,
                    }
                )
            except Exception as exc:
                conn.sendall(f"ERROR SCORE {exc}\n".encode())
                continue

            score_value = score_response.get("score", 0.0)
            accepted = score_response.get("accepted", False)

            result_payload = {
                "question_id": key,
                "question_title": question_title,
                "question_content": question_content,
                "best_answer": best_answer,
                "llm_answer": llm_answer,
                "score": score_value,
                "accepted": accepted,
                "scoring_latency_ms": score_response.get("elapsed_ms"),
            }

            cache.put(key, result_payload)
            latency = time.time() - start
            cache.record_latency(latency)

            response = {
                "question_id": key,
                "score": score_value,
                "accepted": accepted,
                "source": "origin",
            }
            conn.sendall(
                f"MISS {key} ({latency:.4f}s)\n{json.dumps(response)}\n".encode()
            )

            try:
                storage_client.request(
                    {
                        "action": "store_result",
                        "data": {
                            "id_pregunta": key,
                            "pregunta": question_title,
                            "respuesta_dataset": best_answer,
                            "respuesta_llm": llm_answer,
                            "score": score_value,
                            "aceptado": accepted,
                        },
                    }
                )
                storage_client.request(
                    {
                        "action": "record_metrics",
                        "data": {"hit": False, "latency": latency, "score": score_value},
                    }
                )
            except Exception as exc:
                print(f"[Cache] No se pudo persistir el resultado: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
