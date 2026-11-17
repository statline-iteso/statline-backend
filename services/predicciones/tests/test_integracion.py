"""Runs the real SQL against PostgreSQL with the Prisma migrations applied.

Skipped unless DATABASE_URL is set. Each test seeds synthetic games inside one transaction and
rolls it back, so the database is left as it was. CI runs `pytest -m integration`.
"""

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from fabrica import generar_datos

from predicciones.datos import cargar_lineas, cargar_partidos, cargar_partidos_programados
from predicciones.registro import cargar_activo, entrenar_y_registrar
from predicciones.schemas import Deporte, TipoInferencia

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"),
]

LIGA_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "liga-test"))


def _id(texto: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, texto))


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[object]]:
    conexion = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        yield conexion
    finally:
        conexion.rollback()
        conexion.close()


def _sembrar(conn: psycopg.Connection[object], deporte: Deporte, partidos: int) -> None:
    datos_p, datos_l = generar_datos(deporte, partidos=partidos, seed=31)
    conn.execute(
        "INSERT INTO liga (id, nombre, deporte, temporada, proveedor, proveedor_liga_id)"
        " VALUES (%s, 'Prueba', %s::deporte, '2025-2026', 'demo', %s)",
        (LIGA_ID, deporte.value, _id(f"liga-{deporte.value}")),
    )
    equipos = set(datos_p["local_id"]) | set(datos_p["visita_id"])
    for equipo in equipos:
        conn.execute(
            "INSERT INTO equipo (id, liga_id, nombre, proveedor_id) VALUES (%s, %s, %s, %s)",
            (_id(equipo), LIGA_ID, equipo, equipo),
        )
    for fila in datos_p.itertuples(index=False):
        conn.execute(
            "INSERT INTO partido (id, liga_id, local_id, visita_id, fecha, jornada, temporada,"
            " estatus, marcador_local, marcador_visita, proveedor_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, '2025-2026', 'FINALIZADO', %s, %s, %s)",
            (
                _id(fila.partido_id),
                LIGA_ID,
                _id(fila.local_id),
                _id(fila.visita_id),
                fila.fecha,
                int(fila.jornada),
                int(fila.marcador_local),
                int(fila.marcador_visita),
                fila.proveedor_id,
            ),
        )
    objetivos = [c for c in datos_l.columns if c not in _NO_METRICAS]
    for jugador in set(datos_l["jugador_id"]):
        conn.execute(
            "INSERT INTO jugador (id, deporte, nombre, proveedor_id) VALUES (%s, %s::deporte,"
            " %s, %s)",
            (_id(jugador), deporte.value, jugador, jugador),
        )
    for fila in datos_l.to_dict("records"):
        metricas = _anidar({o: int(fila[o]) for o in objetivos if fila[o] == fila[o]})
        conn.execute(
            "INSERT INTO estadistica_jugador_partido (id, partido_id, jugador_id, equipo_id,"
            " deporte, minutos, metricas) VALUES (%s, %s, %s, %s, %s::deporte, %s, %s::jsonb)",
            (
                str(uuid.uuid4()),
                _id(fila["partido_id"]),
                _id(fila["jugador_id"]),
                _id(fila["equipo_id"]),
                deporte.value,
                int(fila["minutos"]),
                json.dumps(metricas),
            ),
        )


def _anidar(planas: dict[str, int]) -> dict[str, object]:
    """Turn dotted keys back into nested groups, as the NFL schema stores them."""
    anidado: dict[str, object] = {}
    for clave, valor in planas.items():
        grupo, _, campo = clave.partition(".")
        if campo:
            subgrupo = anidado.setdefault(grupo, {})
            assert isinstance(subgrupo, dict)
            subgrupo[campo] = valor
        else:
            anidado[clave] = valor
    return anidado


_NO_METRICAS = {
    "partido_id", "jugador_id", "equipo_id", "fecha", "local_id", "visita_id", "minutos", "es_demo",
}  # fmt: skip


def test_cargar_partidos_y_lineas_con_postgres(conn: psycopg.Connection[object]) -> None:
    _sembrar(conn, Deporte.BASQUETBOL, partidos=40)
    partidos = cargar_partidos(conn, Deporte.BASQUETBOL)  # type: ignore[arg-type]
    assert len(partidos) == 40
    assert partidos["es_demo"].all()
    assert partidos["fecha"].dt.tz is not None
    lineas = cargar_lineas(conn, Deporte.BASQUETBOL)  # type: ignore[arg-type]
    assert {"puntos", "rebotes", "asistencias", "minutos"} <= set(lineas.columns)
    assert lineas["puntos"].notna().all()
    assert cargar_partidos_programados(conn, Deporte.BASQUETBOL).empty  # type: ignore[arg-type]


def test_entrenar_registrar_y_cargar_activo(
    conn: psycopg.Connection[object], tmp_path: Path
) -> None:
    _sembrar(conn, Deporte.BASQUETBOL, partidos=160)
    resumen = entrenar_y_registrar(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        ahora=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
    )
    assert resumen["activado"] is True
    assert resumen["version"].endswith("-synthetic")
    activo = cargar_activo(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        tmp_path,
    )
    assert activo.modelo_id == resumen["modelo_id"]
    assert set(activo.bundle.clases) == {"L", "V"}


def test_nfl_guarda_grupos_anidados_y_se_aplanan(conn: psycopg.Connection[object]) -> None:
    _sembrar(conn, Deporte.AMERICANO, partidos=30)
    lineas = cargar_lineas(conn, Deporte.AMERICANO)  # type: ignore[arg-type]
    assert {"pase.yardas", "carrera.yardas", "recepcion.yardas"} <= set(lineas.columns)
    assert lineas["pase.yardas"].notna().any()
    assert lineas["pase.yardas"].isna().any()
