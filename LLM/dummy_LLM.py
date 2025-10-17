from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai


class RateLimiter:
    """Limita la cantidad de solicitudes por segundo que procesa el servicio."""

    def __init__(self, max_rps: float | None = None):
        self.min_interval = 1.0 / max_rps if max_rps else 0.0
        self.lock = threading.Lock()
        self.last_call = 0.0

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self.lock:
            now = time.time()
            wait_time = self.min_interval - (now - self.last_call)
            if wait_time > 0:
                time.sleep(wait_time)
                now = time.time()
            self.last_call = now


class GeminiClientError(RuntimeError):
    """Error producido al interactuar con la API de Gemini."""


@dataclass(slots=True)
class GeminiConfig:
    api_key: str
    model: str = "gemini-1.5-flash"
    timeout: float = 15.0
    max_retries: int = 3
    backoff: float = 2.0


class GeminiClient:
    """Cliente liviano y seguro para múltiples hilos sobre la API de Gemini."""

    def __init__(self, config: GeminiConfig):
        if not config.api_key:
            raise ValueError("Se requiere la API key de Gemini (GEMINI_API_KEY)")

        self._config = config
        genai.configure(api_key=config.api_key)
        self._model = genai.GenerativeModel(config.model)
        self._lock = threading.Lock()

    def build_prompt(self, title: str, content: str) -> str:
        title = title.strip() or "(Sin título)"
        content = content.strip() or "(Sin descripción adicional)"
        return (
            "Eres un asistente experto que responde preguntas provenientes de Yahoo! Answers. "
            "Redacta una respuesta clara y completa, justificando los pasos si corresponde. "
            "Pregunta: "
            f"{title}\n\nDetalles adicionales: {content}\n\nRespuesta:"
        )

    def generate_answer(self, title: str, content: str) -> str:
        prompt = self.build_prompt(title, content)
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                with self._lock:
                    response = self._model.generate_content(
                        prompt,
                        request_options={"timeout": self._config.timeout},
                    )
                if not getattr(response, "text", "").strip():
                    raise GeminiClientError("Respuesta vacía de Gemini")
                return response.text.strip()
            except Exception as exc:  # pragma: no cover - robustez ante errores externos
                last_exc = exc
                if attempt >= self._config.max_retries:
                    break
                time.sleep(self._config.backoff * attempt)

        raise GeminiClientError(str(last_exc) if last_exc else "Fallo desconocido de Gemini")


def run_dummy_server(
    host: str,
    port: int,
    max_rps: float,
    max_concurrent: int,
    timeout: float,
    gemini_config: GeminiConfig,
):
    rate_limiter = RateLimiter(max_rps if max_rps > 0 else None)
    semaphore = threading.Semaphore(max_concurrent if max_concurrent > 0 else 1)
    gemini_client = GeminiClient(gemini_config)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(
        "[GeminiLLM] Servidor escuchando en "
        f"{host}:{port} · max_rps={max_rps} · max_concurrent={max_concurrent}"
    )

    def handle_client(conn: socket.socket):
        with conn, semaphore:
            conn.settimeout(timeout)
            try:
                data = conn.recv(4096).decode().strip()
            except socket.timeout:
                conn.sendall(json.dumps({"error": "timeout"}).encode() + b"\n")
                return

            if not data:
                return

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                conn.sendall(json.dumps({"error": "invalid_json"}).encode() + b"\n")
                return

            rate_limiter.acquire()

            title = payload.get("title", "")
            content = payload.get("content", "")

            try:
                answer = gemini_client.generate_answer(title, content)
                response = {"generated_answer": answer}
            except GeminiClientError as exc:
                response = {"error": str(exc)}

            conn.sendall(json.dumps(response).encode() + b"\n")

    while True:
        connection, _ = server.accept()
        threading.Thread(target=handle_client, args=(connection,), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servicio LLM basado en Gemini")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument(
        "--max_rps", type=float, default=5.0, help="Solicitudes por segundo permitidas"
    )
    parser.add_argument(
        "--max_concurrent", type=int, default=4, help="Número máximo de solicitudes simultáneas"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Tiempo máximo de espera por conexión en segundos",
    )
    parser.add_argument(
        "--gemini_model",
        default=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        help="Modelo de Gemini a utilizar",
    )
    parser.add_argument(
        "--gemini_timeout",
        type=float,
        default=float(os.getenv("GEMINI_TIMEOUT", "15")),
        help="Timeout (s) por solicitud a Gemini",
    )
    parser.add_argument(
        "--gemini_retries",
        type=int,
        default=int(os.getenv("GEMINI_RETRIES", "3")),
        help="Reintentos máximos frente a errores transitorios",
    )
    parser.add_argument(
        "--gemini_backoff",
        type=float,
        default=float(os.getenv("GEMINI_BACKOFF", "2.0")),
        help="Factor multiplicador de backoff exponencial",
    )
    parser.add_argument(
        "--gemini_api_key",
        default=os.getenv("GEMINI_API_KEY"),
        help="API key de Gemini (también puede venir de la variable de entorno)",
    )

    opts = parser.parse_args()
    config = GeminiConfig(
        api_key=opts.gemini_api_key,
        model=opts.gemini_model,
        timeout=opts.gemini_timeout,
        max_retries=opts.gemini_retries,
        backoff=opts.gemini_backoff,
    )
    run_dummy_server(
        opts.host,
        opts.port,
        opts.max_rps,
        opts.max_concurrent,
        opts.timeout,
        config,
    )
