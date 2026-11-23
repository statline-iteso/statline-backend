"""PostgreSQL data access. The only module with SQL; every query is parameterized.

Tables are owned by Prisma Migrate (services/api/prisma/schema.prisma). Synthetic games from the
demo seeder are flagged with `es_demo`: their provider ids start with `demo-` (D-29).
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from predicciones.errores import SinModeloActivoError
from predicciones.schemas import Deporte, TipoInferencia

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
SELECT p.id::text AS partido_id, p.fecha, p.liga_id::text AS liga_id, p.jornada,
       p.local_id::text AS local_id, p.visita_id::text AS visita_id,
       p.marcador_local, p.marcador_visita, p.proveedor_id LIKE %s AS es_demo
FROM partido p
JOIN liga l ON l.id = p.liga_id
WHERE l.deporte = %s::deporte AND p.estatus = %s::estatus_partido
ORDER BY p.fecha, p.id
"""

_SQL_LINEAS = """
SELECT e.partido_id::text AS partido_id, e.jugador_id::text AS jugador_id,
       e.equipo_id::text AS equipo_id, p.fecha, p.local_id::text AS local_id,
       p.visita_id::text AS visita_id, e.minutos, e.metricas,
       p.proveedor_id LIKE %s AS es_demo
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


_SQL_MODELO_ACTIVO = """
SELECT id::text, version, nombre_metrica, metrica_error FROM modelo_prediccion
WHERE deporte = %s::deporte AND tipo = %s::tipo_inferencia AND activo
"""

_SQL_JUGADORES = """
SELECT j.id::text AS jugador_id, j.equipo_id::text AS equipo_id
FROM jugador j
WHERE j.deporte = %s::deporte AND j.equipo_id IS NOT NULL
ORDER BY j.id
"""

_SQL_BORRAR_PRONOSTICO = (
    "DELETE FROM pronostico_partido WHERE partido_id = %s::uuid AND modelo_id = %s::uuid"
)
_SQL_INSERTAR_PRONOSTICO = """
INSERT INTO pronostico_partido (id, partido_id, modelo_id, prob_local, prob_empate, prob_visita,
    marcador_esperado_local, marcador_esperado_visita, generado_en)
VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
"""

_SQL_BORRAR_PROYECCION = (
    "DELETE FROM proyeccion_jugador WHERE jugador_id = %s::uuid AND partido_id = %s::uuid"
    " AND modelo_id = %s::uuid"
)
_SQL_INSERTAR_PROYECCION = """
INSERT INTO proyeccion_jugador (id, jugador_id, partido_id, modelo_id, metricas, generado_en)
VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s)
"""

_SQL_PRONOSTICOS_RESUELTOS = """
SELECT pp.prob_local, pp.prob_empate, pp.prob_visita, p.marcador_local, p.marcador_visita
FROM pronostico_partido pp
JOIN partido p ON p.id = pp.partido_id
WHERE pp.modelo_id = %s::uuid AND p.estatus = 'FINALIZADO' AND pp.generado_en < p.fecha
  AND p.marcador_local IS NOT NULL AND p.marcador_visita IS NOT NULL
"""

_SQL_PROYECCIONES_RESUELTAS = """
SELECT pj.metricas AS proyeccion, e.metricas AS estadistica
FROM proyeccion_jugador pj
JOIN partido p ON p.id = pj.partido_id
JOIN estadistica_jugador_partido e
  ON e.partido_id = pj.partido_id AND e.jugador_id = pj.jugador_id
WHERE pj.modelo_id = %s::uuid AND p.estatus = 'FINALIZADO' AND pj.generado_en < p.fecha
"""


def _filas_dict(cur: psycopg.Cursor[Any]) -> list[dict[str, Any]]:
    columnas = _columnas(cur)
    return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]


def cargar_info_modelo_activo(
    conn: psycopg.Connection[Any], deporte: Deporte, tipo: TipoInferencia
) -> dict[str, Any]:
    """Id, version, metric name and value of the active model. Does not load the artifact."""
    with conn.cursor() as cur:
        cur.execute(_SQL_MODELO_ACTIVO, (deporte.value, tipo.value))
        fila = cur.fetchone()
    if fila is None:
        raise SinModeloActivoError(f"no hay modelo activo para {deporte.value}/{tipo.value}")
    return {
        "id": str(fila[0]),
        "version": str(fila[1]),
        "nombre_metrica": str(fila[2]),
        "metrica_error": float(fila[3]),
    }


def cargar_jugadores(conn: psycopg.Connection[Any], deporte: Deporte) -> pd.DataFrame:
    """Players of a sport with a current team: jugador_id, equipo_id."""
    with conn.cursor() as cur:
        cur.execute(_SQL_JUGADORES, (deporte.value,))
        filas = cur.fetchall()
        columnas = _columnas(cur)
    return pd.DataFrame(filas, columns=pd.Index(columnas))


def reemplazar_pronosticos(
    conn: psycopg.Connection[Any],
    modelo_id: str,
    filas: Sequence[Mapping[str, Any]],
) -> None:
    """Replace the forecasts of these games for this model (no unique key in the table)."""
    if not filas:
        return
    ahora = datetime.now(UTC)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(_SQL_BORRAR_PRONOSTICO, [(f["partido_id"], modelo_id) for f in filas])
        cur.executemany(
            _SQL_INSERTAR_PRONOSTICO,
            [
                (
                    f["id"],
                    f["partido_id"],
                    modelo_id,
                    f["prob_local"],
                    f["prob_empate"],
                    f["prob_visita"],
                    f["marcador_esperado_local"],
                    f["marcador_esperado_visita"],
                    ahora,
                )
                for f in filas
            ],
        )


def reemplazar_proyecciones(
    conn: psycopg.Connection[Any],
    modelo_id: str,
    filas: Sequence[Mapping[str, Any]],
) -> None:
    """Replace the projections of these (player, game) pairs for this model."""
    if not filas:
        return
    ahora = datetime.now(UTC)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            _SQL_BORRAR_PROYECCION,
            [(f["jugador_id"], f["partido_id"], modelo_id) for f in filas],
        )
        cur.executemany(
            _SQL_INSERTAR_PROYECCION,
            [
                (
                    f["id"],
                    f["jugador_id"],
                    f["partido_id"],
                    modelo_id,
                    Jsonb(f["metricas"]),
                    ahora,
                )
                for f in filas
            ],
        )


def cargar_pronosticos_resueltos(
    conn: psycopg.Connection[Any], modelo_id: str
) -> list[dict[str, Any]]:
    """Forecasts of one model for finished games with a score."""
    with conn.cursor() as cur:
        cur.execute(_SQL_PRONOSTICOS_RESUELTOS, (modelo_id,))
        return _filas_dict(cur)


def cargar_proyecciones_resueltas(
    conn: psycopg.Connection[Any], modelo_id: str
) -> list[dict[str, Any]]:
    """Projections of one model for finished games, with the actual stat line (`estadistica`)."""
    with conn.cursor() as cur:
        cur.execute(_SQL_PROYECCIONES_RESUELTAS, (modelo_id,))
        return _filas_dict(cur)
