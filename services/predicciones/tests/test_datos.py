import os

import psycopg
import pytest

from predicciones.datos import aplanar_metricas, cargar_lineas, cargar_partidos
from predicciones.deportes import clase_resultado
from predicciones.schemas import Deporte


def test_aplanar_metricas_plano_y_anidado() -> None:
    metricas = {
        "puntos": 12,
        "pase": {"yardas": 250, "touchdowns": 2},
        "carrera": {"yardas": -3.5},
        "marca": True,
        "nota": "texto",
    }
    assert aplanar_metricas(metricas) == {
        "puntos": 12.0,
        "pase.yardas": 250.0,
        "pase.touchdowns": 2.0,
        "carrera.yardas": -3.5,
    }


def test_resultado_empate_solo_existe_en_futbol() -> None:
    assert clase_resultado(Deporte.FUTBOL, 1, 1) == "E"
    assert clase_resultado(Deporte.BASQUETBOL, 100, 100) is None
    assert clase_resultado(Deporte.AMERICANO, 20, 27) == "V"
    assert clase_resultado(Deporte.FUTBOL, 2, 0) == "L"


class _Columna:
    def __init__(self, name: str) -> None:
        self.name = name


class _Cursor:
    description = (_Columna("partido_id"), _Columna("metricas"))

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql, self.params = sql, params

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


class _Conexion:
    def cursor(self) -> _Cursor:
        return _Cursor()


def test_cargar_lineas_sin_filas_devuelve_columnas_base() -> None:
    df = cargar_lineas(_Conexion(), Deporte.FUTBOL)  # type: ignore[arg-type]
    assert df.empty
    assert "jugador_id" in df.columns


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
def test_cargar_partidos_contra_postgres() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        df = cargar_partidos(conn, Deporte.BASQUETBOL)
        lineas = cargar_lineas(conn, Deporte.BASQUETBOL)
    assert {"partido_id", "fecha", "local_id", "visita_id", "es_demo"} <= set(df.columns)
    assert {"partido_id", "jugador_id", "minutos"} <= set(lineas.columns)
