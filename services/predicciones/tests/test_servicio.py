"""Pure transforms of the prediction endpoints: no database, synthetic data from fabrica."""

import math

import pandas as pd
import pytest
from fabrica import generar_datos

from predicciones import servicio
from predicciones.datos import aplanar_metricas
from predicciones.modelos.jugador import entrenar_jugador
from predicciones.modelos.resultado import entrenar_resultado
from predicciones.schemas import Deporte


@pytest.fixture(scope="module")
def modelo_resultado() -> tuple[object, pd.DataFrame, pd.DataFrame]:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=200, seed=11)
    bundle = entrenar_resultado(Deporte.BASQUETBOL, partidos).bundle
    programados = partidos.tail(4).copy()
    programados[["marcador_local", "marcador_visita"]] = float("nan")
    return bundle, partidos.iloc[:-4], programados


@pytest.fixture(scope="module")
def modelo_jugador() -> tuple[object, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    partidos, lineas = generar_datos(Deporte.BASQUETBOL, partidos=120, seed=13)
    bundle = entrenar_jugador(Deporte.BASQUETBOL, lineas, estimadores=20).bundle
    programados = partidos.tail(2).copy()
    programados[["marcador_local", "marcador_visita"]] = float("nan")
    historial = lineas[~lineas["partido_id"].isin(set(programados["partido_id"]))]
    jugadores = lineas[["jugador_id", "equipo_id"]].drop_duplicates("jugador_id")
    return bundle, historial, programados, jugadores


def test_pronosticos_una_fila_por_partido_con_probabilidades_validas(
    modelo_resultado: tuple[object, pd.DataFrame, pd.DataFrame],
) -> None:
    bundle, historial, programados = modelo_resultado
    filas = servicio.pronosticos_para(bundle, historial, programados)  # type: ignore[arg-type]
    assert len(filas) == 4
    for fila in filas:
        assert fila["prob_empate"] == 0.0
        assert fila["prob_local"] + fila["prob_visita"] == pytest.approx(1.0)
        assert math.isfinite(fila["marcador_esperado_local"])


def test_pronosticos_filtros_por_ids_sin_distinguir_mayusculas_y_jornada(
    modelo_resultado: tuple[object, pd.DataFrame, pd.DataFrame],
) -> None:
    bundle, historial, programados = modelo_resultado
    elegido = str(programados["partido_id"].iloc[2]).upper()
    filas = servicio.pronosticos_para(
        bundle,  # type: ignore[arg-type]
        historial,
        programados,
        partido_ids=[elegido],
    )
    assert [f["partido_id"] for f in filas] == [elegido.lower()]
    assert servicio.pronosticos_para(bundle, historial, programados, jornada=12345) == []  # type: ignore[arg-type]


def test_proyecciones_un_partido_proximo_por_jugador(
    modelo_jugador: tuple[object, pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    bundle, historial, programados, jugadores = modelo_jugador
    filas = servicio.proyecciones_para(bundle, historial, programados, jugadores)  # type: ignore[arg-type]
    assert filas
    jugadores_vistos = [f["jugador_id"] for f in filas]
    assert len(jugadores_vistos) == len(set(jugadores_vistos))
    partidos = programados.set_index("partido_id")
    for fila in filas:
        assert fila["partido_id"] in partidos.index
        assert set(fila["metricas"]) == {"puntos", "rebotes", "asistencias"}
        equipo = jugadores.set_index("jugador_id").loc[fila["jugador_id"], "equipo_id"]
        assert equipo in (
            partidos.loc[fila["partido_id"], "local_id"],
            partidos.loc[fila["partido_id"], "visita_id"],
        )


def test_proyecciones_filtra_por_jugador(
    modelo_jugador: tuple[object, pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    bundle, historial, programados, jugadores = modelo_jugador
    objetivo = str(jugadores["jugador_id"].iloc[0])
    filas = servicio.proyecciones_para(
        bundle,  # type: ignore[arg-type]
        historial,
        programados,
        jugadores,
        jugador_ids=[objetivo],
    )
    assert [f["jugador_id"] for f in filas] in ([objetivo], [])


def test_proyecciones_sin_partidos_o_jugadores_es_vacio(
    modelo_jugador: tuple[object, pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    bundle, historial, programados, jugadores = modelo_jugador
    assert servicio.proyecciones_para(bundle, historial, programados.iloc[0:0], jugadores) == []  # type: ignore[arg-type]
    assert servicio.proyecciones_para(bundle, historial, programados, jugadores.iloc[0:0]) == []  # type: ignore[arg-type]


def test_precision_resultado_cuenta_aciertos_y_log_loss_sin_empates_en_nba() -> None:
    filas = [
        {
            "prob_local": 0.9,
            "prob_empate": 0.0,
            "prob_visita": 0.1,
            "marcador_local": 100,
            "marcador_visita": 90,
        },
        {
            "prob_local": 0.8,
            "prob_empate": 0.0,
            "prob_visita": 0.2,
            "marcador_local": 80,
            "marcador_visita": 95,
        },
        {
            "prob_local": 0.5,
            "prob_empate": 0.0,
            "prob_visita": 0.5,
            "marcador_local": 70,
            "marcador_visita": 70,
        },
    ]
    r = servicio.precision_resultado(Deporte.BASQUETBOL, filas)
    assert r["n"] == 2  # the tie is not a class in NBA
    assert r["aciertos"] == 1
    assert r["accuracy"] == pytest.approx(0.5)
    assert r["logLoss"] == pytest.approx((-math.log(0.9) - math.log(0.2)) / 2)


def test_precision_futbol_acierta_el_empate() -> None:
    fila = {
        "prob_local": 0.2,
        "prob_empate": 0.6,
        "prob_visita": 0.2,
        "marcador_local": 1,
        "marcador_visita": 1,
    }
    r = servicio.precision_resultado(Deporte.FUTBOL, [fila])
    assert r["accuracy"] == 1.0
    assert r["logLoss"] == pytest.approx(-math.log(0.6))


def test_precision_sin_filas_no_inventa_metricas() -> None:
    r = servicio.precision_resultado(Deporte.FUTBOL, [])
    assert r == {"n": 0, "aciertos": 0, "accuracy": None, "logLoss": None}


def test_precision_proyeccion_mae_por_objetivo_y_sin_dato_real() -> None:
    filas = [
        {
            "proyeccion": {"puntos": 10.0, "rebotes": 4.0},
            "estadistica": {"puntos": 12, "rebotes": 4, "asistencias": 3},
        },
        {"proyeccion": {"puntos": 8.0}, "estadistica": {"puntos": 9}},
    ]
    r = servicio.precision_proyeccion(Deporte.BASQUETBOL, filas)
    assert r["n"] == 2
    assert r["porObjetivo"]["puntos"] == {"n": 2, "mae": pytest.approx(1.5)}
    assert r["porObjetivo"]["rebotes"] == {"n": 1, "mae": 0.0}
    assert r["porObjetivo"]["asistencias"] == {"n": 0, "mae": None}


def test_precision_nfl_compara_grupos_aplanados() -> None:
    filas = [{"proyeccion": {"pase.yardas": 240.0}, "estadistica": {"pase": {"yardas": 250}}}]
    r = servicio.precision_proyeccion(Deporte.AMERICANO, filas)
    assert r["porObjetivo"]["pase.yardas"] == {"n": 1, "mae": 10.0}


def test_aplanar_metricas_conserva_solo_numeros() -> None:
    assert aplanar_metricas({"puntos": 3, "pase": {"yardas": 2.5}, "ok": True, "x": "y"}) == {
        "puntos": 3.0,
        "pase.yardas": 2.5,
    }
