"""FastAPI app. Only reachable inside the cluster: the Node API proxies the public routes.

Routes: /healthz, /readyz, /metrics and the prediction endpoints (SL-37, SL-38):
POST /pronosticos/generar, POST /proyecciones/generar, GET /precision,
POST /modelos/reentrenar, POST /modelos/{id}/activar. Requests are snake_case, responses are
camelCase (docs/ARCHITECTURE.md §5). Every request opens its own PostgreSQL connection (D-20).
"""

import time
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from predicciones import servicio
from predicciones.config import Settings
from predicciones.errores import (
    ArtefactoInvalidoError,
    BaseDatosNoDisponibleError,
    DatosInsuficientesError,
    ModeloNoEncontradoError,
    SinModeloActivoError,
)
from predicciones.schemas import (
    Deporte,
    GenerarPronosticosRequest,
    GenerarProyeccionesRequest,
    ReentrenarRequest,
    TipoInferencia,
)

PETICIONES = Counter(
    "statline_predicciones_requests_total", "Requests", ["method", "path", "status"]
)
LATENCIA = Histogram("statline_predicciones_request_seconds", "Latency", ["method", "path"])
CONEXION_TIMEOUT_S = 5

Conexion = psycopg.Connection[Any]


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


def get_conn(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Conexion]:
    """One connection per request, autocommit: each `conn.transaction()` commits on its own."""
    if not settings.database_url:
        raise BaseDatosNoDisponibleError("DATABASE_URL no configurada")
    try:
        conn = psycopg.connect(
            settings.database_url, connect_timeout=CONEXION_TIMEOUT_S, autocommit=True
        )
    except psycopg.OperationalError as err:
        raise BaseDatosNoDisponibleError("no se pudo conectar a PostgreSQL") from err
    try:
        yield conn
    finally:
        conn.close()


def _error(status: int, codigo: str, mensaje: str, detalles: Any = None) -> JSONResponse:
    cuerpo: dict[str, Any] = {"code": codigo, "message": mensaje}
    if detalles is not None:
        cuerpo["details"] = detalles
    return JSONResponse(status_code=status, content={"error": cuerpo})


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

    @app.exception_handler(SinModeloActivoError)
    def _sin_modelo(_req: Request, exc: SinModeloActivoError) -> JSONResponse:
        return _error(409, "NO_ACTIVE_MODEL", str(exc))

    @app.exception_handler(DatosInsuficientesError)
    def _datos_insuficientes(_req: Request, exc: DatosInsuficientesError) -> JSONResponse:
        return _error(422, "INSUFFICIENT_DATA", str(exc))

    @app.exception_handler(ModeloNoEncontradoError)
    def _no_encontrado(_req: Request, _exc: ModeloNoEncontradoError) -> JSONResponse:
        return _error(404, "NOT_FOUND", "Modelo no encontrado")

    @app.exception_handler(ArtefactoInvalidoError)
    def _artefacto(_req: Request, _exc: ArtefactoInvalidoError) -> JSONResponse:
        return _error(500, "ARTEFACTO_INVALIDO", "El artefacto del modelo no es válido")

    @app.exception_handler(BaseDatosNoDisponibleError)
    def _db_no_disponible(_req: Request, exc: BaseDatosNoDisponibleError) -> JSONResponse:
        return _error(503, "DB_UNAVAILABLE", str(exc))

    @app.exception_handler(psycopg.OperationalError)
    def _db_caida(_req: Request, _exc: psycopg.OperationalError) -> JSONResponse:
        return _error(503, "DB_UNAVAILABLE", "PostgreSQL no disponible")

    @app.exception_handler(RequestValidationError)
    def _validacion(_req: Request, exc: RequestValidationError) -> JSONResponse:
        detalles = [
            {"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return _error(422, "VALIDATION_ERROR", "Solicitud inválida", detalles)

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

    @app.post("/pronosticos/generar")
    def generar_pronosticos(
        body: GenerarPronosticosRequest,
        conn: Annotated[Conexion, Depends(get_conn)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, Any]:
        return servicio.generar_pronosticos(conn, body, Path(settings.artefactos_dir))

    @app.post("/proyecciones/generar")
    def generar_proyecciones(
        body: GenerarProyeccionesRequest,
        conn: Annotated[Conexion, Depends(get_conn)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, Any]:
        return servicio.generar_proyecciones(conn, body, Path(settings.artefactos_dir))

    @app.get("/precision")
    def precision(
        deporte: Deporte,
        tipo: TipoInferencia,
        conn: Annotated[Conexion, Depends(get_conn)],
    ) -> dict[str, Any]:
        return servicio.precision(conn, deporte, tipo)

    @app.post("/modelos/reentrenar")
    def reentrenar(
        body: ReentrenarRequest,
        conn: Annotated[Conexion, Depends(get_conn)],
    ) -> dict[str, Any]:
        return servicio.reentrenar(conn, body)

    @app.post("/modelos/{modelo_id}/activar")
    def activar(modelo_id: str, conn: Annotated[Conexion, Depends(get_conn)]) -> dict[str, Any]:
        return servicio.activar(conn, modelo_id)

    return app


app = create_app()
