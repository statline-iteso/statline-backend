import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fabrica import generar_datos

from predicciones.deportes import OBJETIVOS_JUGADOR
from predicciones.features import (
    RASGOS_EQUIPO,
    features_jugadores,
    features_partidos,
    nombres_features_partido,
)
from predicciones.schemas import Deporte


def _partido(pid: str, dia: int, local: str, visita: str, ml: float | None, mv: float | None):
    return {
        "partido_id": pid,
        "fecha": datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=dia),
        "local_id": local,
        "visita_id": visita,
        "marcador_local": np.nan if ml is None else ml,
        "marcador_visita": np.nan if mv is None else mv,
    }


def test_primer_partido_sin_historia_da_nan_y_descanso_nan() -> None:
    df = pd.DataFrame([_partido("p1", 0, "A", "B", 100, 90)])
    f = features_partidos(df)
    assert math.isnan(f.loc["p1", "local_puntos_favor"])
    assert math.isnan(f.loc["p1", "visita_dias_descanso"])


def test_promedios_usan_solo_partidos_previos() -> None:
    df = pd.DataFrame(
        [
            _partido("p1", 0, "A", "B", 100, 80),  # A gana
            _partido("p2", 1, "B", "A", 70, 90),  # A gana de visita
            _partido("p3", 2, "A", "B", None, None),  # a predecir
        ]
    )
    f = features_partidos(df)
    assert f.loc["p3", "local_puntos_favor"] == pytest.approx(95.0)
    assert f.loc["p3", "local_puntos_contra"] == pytest.approx(75.0)
    assert f.loc["p3", "local_tasa_victorias"] == pytest.approx(1.0)
    assert f.loc["p3", "local_tasa_victorias_local"] == pytest.approx(1.0)
    assert f.loc["p3", "local_tasa_victorias_visita"] == pytest.approx(1.0)
    assert f.loc["p3", "visita_tasa_victorias"] == pytest.approx(0.0)
    assert f.loc["p3", "visita_tasa_victorias_local"] == pytest.approx(0.0)
    assert f.loc["p3", "visita_tasa_victorias_visita"] == pytest.approx(0.0)
    assert f.loc["p3", "local_dias_descanso"] == pytest.approx(1.0)


def test_dias_descanso_se_topa() -> None:
    df = pd.DataFrame([_partido("p1", 0, "A", "B", 1, 0), _partido("p2", 60, "A", "C", None, None)])
    assert features_partidos(df).loc["p2", "local_dias_descanso"] == 14.0


def test_diferencias_son_local_menos_visita() -> None:
    p, _ = generar_datos(Deporte.BASQUETBOL, partidos=60)
    f = features_partidos(p)
    for rasgo in RASGOS_EQUIPO:
        esperado = f[f"local_{rasgo}"] - f[f"visita_{rasgo}"]
        pd.testing.assert_series_equal(f[f"dif_{rasgo}"], esperado, check_names=False)


def test_columnas_coinciden_con_nombres_publicos() -> None:
    p, _ = generar_datos(Deporte.FUTBOL, partidos=20)
    assert list(features_partidos(p).columns) == list(nombres_features_partido())


def test_ventana_invalida_falla() -> None:
    p, _ = generar_datos(Deporte.FUTBOL, partidos=5)
    with pytest.raises(ValueError):
        features_partidos(p, ventana=0)


def test_sin_fuga_resultado_propio_no_entra_en_sus_features() -> None:
    p, _ = generar_datos(Deporte.BASQUETBOL, partidos=120)
    base = features_partidos(p)
    alterado = p.copy()
    objetivo = alterado.index[70]
    alterado.loc[objetivo, "marcador_local"] += 500  # resultado absurdo del propio partido
    assert (
        features_partidos(alterado)
        .loc[p.loc[objetivo, "partido_id"]]
        .equals(base.loc[p.loc[objetivo, "partido_id"]])
    )


def test_sin_fuga_features_iguales_sin_partidos_futuros() -> None:
    p, _ = generar_datos(Deporte.FUTBOL, partidos=120)
    completo = features_partidos(p)
    for idx in (30, 80, 115):
        fecha = p.loc[idx, "fecha"]
        pid = p.loc[idx, "partido_id"]
        recorte = p[(p["fecha"] < fecha) | (p["partido_id"] == pid)]
        recortado = features_partidos(recorte)
        pd.testing.assert_series_equal(completo.loc[pid], recortado.loc[pid], check_names=False)


def test_jugadores_sin_fuga_resultado_propio_no_cuenta() -> None:
    _, lineas = generar_datos(Deporte.BASQUETBOL, partidos=80)
    objetivos = OBJETIVOS_JUGADOR[Deporte.BASQUETBOL]
    base = features_jugadores(lineas, lineas, objetivos)
    alterado = lineas.copy()
    alterado.loc[alterado.index[200], "puntos"] = 999.0
    nuevo = features_jugadores(alterado, alterado, objetivos)
    sin_tocar = alterado.index[200]
    # The line itself is not in its own history: its rolling features are unchanged.
    columnas = [c for c in base.columns if c.startswith("prom_")]
    pd.testing.assert_frame_equal(base.loc[[sin_tocar], columnas], nuevo.loc[[sin_tocar], columnas])


def test_jugadores_promedio_de_ultimos_partidos_del_jugador() -> None:
    fecha = [datetime(2025, 1, d, tzinfo=UTC) for d in (1, 2, 3)]
    historial = pd.DataFrame(
        {
            "partido_id": ["p1", "p2", "p3"],
            "jugador_id": ["j", "j", "j"],
            "equipo_id": ["A", "A", "A"],
            "local_id": ["A", "A", "A"],
            "visita_id": ["B", "B", "B"],
            "fecha": fecha,
            "minutos": [30.0, 20.0, 10.0],
            "puntos": [10.0, 20.0, 30.0],
        }
    )
    consulta = pd.DataFrame(
        {
            "jugador_id": ["j"],
            "equipo_id": ["B"],
            "local_id": ["A"],
            "visita_id": ["B"],
            "fecha": [datetime(2025, 1, 4, tzinfo=UTC)],
        }
    )
    f = features_jugadores(historial, consulta, ("puntos",), ventana=2)
    assert f.loc[0, "prom_puntos"] == pytest.approx(25.0)
    assert f.loc[0, "minutos_prom"] == pytest.approx(15.0)
    assert f.loc[0, "es_local"] == 0.0


def test_jugador_nuevo_da_nan_y_nfl_mantiene_claves_con_punto() -> None:
    _, lineas = generar_datos(Deporte.AMERICANO, partidos=40)
    objetivos = OBJETIVOS_JUGADOR[Deporte.AMERICANO]
    f = features_jugadores(lineas.iloc[:1], lineas.iloc[:1], objetivos)
    assert "prom_pase.yardas" in f.columns
    assert "rival_recepcion.yardas_permitido" in f.columns
    nuevo = lineas.iloc[:1].assign(jugador_id="nadie")
    assert math.isnan(features_jugadores(lineas, nuevo, objetivos).iloc[0]["prom_pase.yardas"])
