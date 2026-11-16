"""Tiny HTTP server for /healthz, /readyz and /metrics (proposal §2.2, every backend service)."""

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ingesta.config import Settings


def crear_handler(db_ok: Callable[[], bool]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._responder(200, b'{"status":"ok"}', "application/json")
            elif self.path == "/readyz":
                if db_ok():
                    self._responder(200, b'{"status":"ready"}', "application/json")
                else:
                    self._responder(503, b'{"status":"not_ready"}', "application/json")
            elif self.path == "/metrics":
                self._responder(200, generate_latest(), CONTENT_TYPE_LATEST)
            else:
                self._responder(404, b'{"error":"not found"}', "application/json")

        def _responder(self, status: int, cuerpo: bytes, tipo: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, format: str, *args: object) -> None:
            pass  # probes every few seconds would flood the logs

    return Handler


def servir(settings: Settings) -> None:  # pragma: no cover - blocking server
    def db_ok() -> bool:
        try:
            with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    ThreadingHTTPServer(("0.0.0.0", settings.health_port), crear_handler(db_ok)).serve_forever()
