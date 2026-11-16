"""FastAPI app. Only reachable inside the cluster: the Node API proxies the public routes.

Implemented: /healthz, /readyz, /metrics and the request/response contract (schemas.py).
Pending (see docs/BACKLOG.md, E5): feature extraction, training, the model registry and the
/generar, /precision and /reentrenar handlers. They answer 501 until then.
"""

import time
from collections.abc import Awaitable, Callable
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from predicciones.config import Settings
from predicciones.schemas import (
    GenerarPronosticosRequest,
    GenerarProyeccionesRequest,
    ReentrenarRequest,
)

PETICIONES = Counter(
    "statline_predicciones_requests_total", "Requests", ["method", "path", "status"]
)
LATENCIA = Histogram("statline_predicciones_request_seconds", "Latency", ["method", "path"])


def get_settings() -> Settings:
    return Settings()


def db_disponible(settings: Annotated[Settings, Depends(get_settings)]) -> bool:
    if not settings.database_url:
        return False
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def _pendiente(issue: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"error": {"code": "NOT_IMPLEMENTED", "message": f"Pendiente: {issue}"}},
    )


def create_app() -> FastAPI:
    app = FastAPI(title="StatLine · predicciones", version="0.1.0")

    @app.middleware("http")
    async def metricas(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inicio = time.perf_counter()
        response = await call_next(request)
        ruta = request.scope.get("route")
        path = getattr(ruta, "path", "unmatched")
        PETICIONES.labels(request.method, path, str(response.status_code)).inc()
        LATENCIA.labels(request.method, path).observe(time.perf_counter() - inicio)
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(ok: Annotated[bool, Depends(db_disponible)]) -> JSONResponse:
        if ok:
            return JSONResponse({"status": "ready", "checks": {"db": "ok"}})
        return JSONResponse({"status": "not_ready", "checks": {"db": "down"}}, status_code=503)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/pronosticos/generar", status_code=202)
    def generar_pronosticos(body: GenerarPronosticosRequest) -> JSONResponse:
        # TODO(SL-34, SL-37): load the active RESULTADO_PARTIDO model for body.deporte, build
        # features for the games of body.jornada and write PronosticoPartido rows.
        return _pendiente("SL-34 / SL-37")

    @app.post("/proyecciones/generar", status_code=202)
    def generar_proyecciones(body: GenerarProyeccionesRequest) -> JSONResponse:
        # TODO(SL-35, SL-37): Gradient Boosting per metric, write ProyeccionJugador rows.
        return _pendiente("SL-35 / SL-37")

    @app.post("/modelos/reentrenar", status_code=202)
    def reentrenar(body: ReentrenarRequest) -> JSONResponse:
        # TODO(SL-36, SL-38): train, validate against the baseline, register a new
        # ModeloPrediccion version (inactive until POST /api/modelos/:id/activar).
        return _pendiente("SL-36 / SL-38")

    return app


app = create_app()
