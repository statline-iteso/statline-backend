"""PostgreSQL data access. The only module with SQL; every query is parameterized.

Tables are owned by Prisma Migrate (services/api/prisma/schema.prisma). Synthetic games from the
demo seeder are flagged with `es_demo`: their provider ids start with `demo-` (D-16).
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd
import psycopg

from predicciones.schemas import Deporte

PREFIJO_DEMO = "demo-%"
LIMITE_PROGRAMADOS_DEFAULT = 500

PARTIDO_COLUMNAS = (
    "partido_id",
    "fecha",
    "liga_id",
    "jornada",
    "local_id",
    "visita_id",
    "marcador_local",
    "marcador_visita",
    "es_demo",
)

_SQL_PARTIDOS = """
SELECT p.id::text, p.fecha, p.liga_id::text, p.jornada, p.local_id::text, p.visita_id::text,
       p.marcador_local, p.marcador_visita, p.proveedor_id LIKE %s
FROM partido p
JOIN liga l ON l.id = p.liga_id
WHERE l.deporte = %s::deporte AND p.estatus = %s::estatus_partido
ORDER BY p.fecha, p.id
"""

_SQL_LINEAS = """
SELECT e.partido_id::text, e.jugador_id::text, e.equipo_id::text, p.fecha,
       p.local_id::text, p.visita_id::text, e.minutos, e.metricas, p.proveedor_id LIKE %s
FROM estadistica_jugador_partido e
JOIN partido p ON p.id = e.partido_id
WHERE e.deporte = %s::deporte AND p.estatus = 'FINALIZADO'
ORDER BY p.fecha, e.partido_id, e.jugador_id
"""


def aplanar_metricas(metricas: Mapping[str, Any], prefijo: str = "") -> dict[str, float]:
    """Flatten a metricas JSONB object: nested groups get dotted keys (`pase.yardas`).

    Only numeric leaves are kept. Booleans and strings are skipped (none exist in the schemas).
    """
    plano: dict[str, float] = {}
    for clave, valor in metricas.items():
        nombre = f"{prefijo}{clave}"
        if isinstance(valor, Mapping):
            plano.update(aplanar_metricas(valor, f"{nombre}."))
        elif isinstance(valor, int | float) and not isinstance(valor, bool):
            plano[nombre] = float(valor)
    return plano


def _frame(
    filas: list[tuple[Any, ...]], columnas: list[str], numericas: tuple[str, ...]
) -> pd.DataFrame:
    df = pd.DataFrame(filas, columns=pd.Index(columnas))
    for columna in numericas:
        df[columna] = pd.to_numeric(df[columna])
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], utc=True)
    return df


def _columnas(cursor: psycopg.Cursor[Any]) -> list[str]:
    return [columna.name for columna in cursor.description or []]


def cargar_partidos(conn: psycopg.Connection[Any], deporte: Deporte) -> pd.DataFrame:
    """Finished games of a sport, oldest first. Used for training and as team history."""
    with conn.cursor() as cur:
        cur.execute(_SQL_PARTIDOS, (PREFIJO_DEMO, deporte.value, "FINALIZADO"))
        filas = cur.fetchall()
        columnas = _columnas(cur)
    df = _frame(
        filas,
        columnas,
        ("jornada", "marcador_local", "marcador_visita"),
    )
    df["es_demo"] = df["es_demo"].astype(bool)
    return df


def cargar_partidos_programados(
    conn: psycopg.Connection[Any],
    deporte: Deporte,
    *,
    limite: int = LIMITE_PROGRAMADOS_DEFAULT,
) -> pd.DataFrame:
    """Scheduled games (no score yet), soonest first. Inputs for inference."""
    sql = _SQL_PARTIDOS.replace("ORDER BY p.fecha, p.id", "ORDER BY p.fecha, p.id LIMIT %s")
    with conn.cursor() as cur:
        cur.execute(sql, (PREFIJO_DEMO, deporte.value, "PROGRAMADO", limite))
        filas = cur.fetchall()
        columnas = _columnas(cur)
    df = _frame(filas, columnas, ("jornada", "marcador_local", "marcador_visita"))
    df["es_demo"] = df["es_demo"].astype(bool)
    return df


def cargar_lineas(conn: psycopg.Connection[Any], deporte: Deporte) -> pd.DataFrame:
    """Player lines of finished games with the metrics flattened into columns.

    Columns: partido_id, jugador_id, equipo_id, fecha, local_id, visita_id, minutos, es_demo,
    and one column per metric key (`puntos`, or `pase.yardas` for NFL). A metric the player did
    not record (e.g. no passing group for a receiver) is NaN.
    """
    with conn.cursor() as cur:
        cur.execute(_SQL_LINEAS, (PREFIJO_DEMO, deporte.value))
        filas = cur.fetchall()
        columnas = _columnas(cur)
    base = pd.DataFrame(filas, columns=pd.Index(columnas))
    if base.empty:
        return _lineas_vacias()
    planos = pd.DataFrame([aplanar_metricas(m) for m in base["metricas"]])
    df = pd.concat([base.drop(columns=["metricas"]).reset_index(drop=True), planos], axis=1)
    df["fecha"] = pd.to_datetime(df["fecha"], utc=True)
    df["minutos"] = pd.to_numeric(df["minutos"])
    df["es_demo"] = df["es_demo"].astype(bool)
    return df


def _lineas_vacias() -> pd.DataFrame:
    columnas = [
        "partido_id",
        "jugador_id",
        "equipo_id",
        "fecha",
        "local_id",
        "visita_id",
        "minutos",
        "es_demo",
    ]
    return pd.DataFrame({columna: pd.Series(dtype=object) for columna in columnas})
