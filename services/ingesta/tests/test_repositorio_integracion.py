"""Runs the real SQL against PostgreSQL with the Prisma migrations applied.

Skipped unless DATABASE_URL is set. CI starts a postgres:16 service, applies
services/api/prisma/migrations and runs `pytest -m integration`.
"""

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from ingesta.modelos import (
    Deporte,
    EquipoNorm,
    EstadisticaNorm,
    EstatusPartido,
    JugadorNorm,
    PartidoNorm,
)
from ingesta.repositorio import LigaNoSembradaError, RepositorioPostgres

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"),
]


@pytest.fixture
def repo() -> RepositorioPostgres:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    conn.execute(
        "TRUNCATE estadistica_jugador_partido, partido, jugador, equipo, liga, ejecucion_ingesta"
        " CASCADE"
    )
    conn.execute(
        "INSERT INTO liga (id, nombre, deporte, temporada, proveedor, proveedor_liga_id)"
        " VALUES (%s, 'NBA', 'BASQUETBOL', '2025-2026', 'api-sports', '12')",
        (str(uuid.uuid4()),),
    )
    return RepositorioPostgres(conn)


def _partido(estatus: EstatusPartido, local: int | None) -> PartidoNorm:
    return PartidoNorm(
        proveedor_id="414001",
        fecha=datetime(2026, 11, 14, 0, 30, tzinfo=UTC),
        temporada="2025-2026",
        estatus=estatus,
        local=EquipoNorm("140", "Denver Nuggets"),
        visita=EquipoNorm("145", "Los Angeles Lakers"),
        marcador_local=local,
        marcador_visita=None if local is None else 111,
    )


def test_ciclo_completo_es_idempotente(repo: RepositorioPostgres) -> None:
    liga_id = repo.liga_id(Deporte.BASQUETBOL, "api-sports", "12")
    ejecucion = repo.iniciar_ejecucion(Deporte.BASQUETBOL, "api-sports")

    # First seen as scheduled, then as final: same row, updated score.
    primero = repo.guardar_partido(liga_id, _partido(EstatusPartido.PROGRAMADO, None))
    partido_id = repo.guardar_partido(liga_id, _partido(EstatusPartido.FINALIZADO, 118))
    assert primero == partido_id

    linea = EstadisticaNorm(
        "414001", "140", JugadorNorm("2001", "N. Jokic"), 36, {"puntos": 31, "rebotes": 14}
    )
    repo.guardar_estadistica(Deporte.BASQUETBOL, liga_id, partido_id, linea)
    repo.guardar_estadistica(Deporte.BASQUETBOL, liga_id, partido_id, linea)  # re-run
    repo.finalizar_ejecucion(ejecucion, exitosa=True, registros=2, peticiones=2, error=None)

    conn = repo._conn
    assert conn.execute("SELECT count(*) FROM equipo").fetchone() == (2,)
    assert conn.execute("SELECT estatus::text, marcador_local FROM partido").fetchone() == (
        "FINALIZADO",
        118,
    )
    # JSONB containment uses the GIN index (jsonb_path_ops).
    fila = conn.execute(
        "SELECT minutos FROM estadistica_jugador_partido WHERE metricas @> %s::jsonb",
        ('{"puntos": 31}',),
    ).fetchone()
    assert fila == (36,)
    assert conn.execute("SELECT count(*) FROM estadistica_jugador_partido").fetchone() == (1,)
    assert conn.execute(
        "SELECT estatus::text, peticiones_usadas, finalizada_en IS NOT NULL FROM ejecucion_ingesta"
    ).fetchone() == ("EXITOSA", 2, True)


def test_liga_no_sembrada(repo: RepositorioPostgres) -> None:
    with pytest.raises(LigaNoSembradaError):
        repo.liga_id(Deporte.FUTBOL, "api-sports", "262")
