import math

import numpy as np
import pandas as pd
import pytest
from fabrica import generar_datos

from predicciones.deportes import CLASES_RESULTADO
from predicciones.errores import DatosInsuficientesError
from predicciones.features import features_partidos
from predicciones.modelos.base import particion_temporal
from predicciones.modelos.resultado import entrenar_resultado, predecir_resultado
from predicciones.schemas import Deporte, TipoInferencia


def test_basquetbol_supera_al_baseline_con_senal() -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=400, seed=3)
    r = entrenar_resultado(Deporte.BASQUETBOL, partidos)
    assert r.nombre_metrica == "log_loss"
    assert r.tipo is TipoInferencia.RESULTADO_PARTIDO
    assert r.supera_baseline, (r.metrica, r.baseline)
    assert r.n_test > 0
    assert r.n_train + r.n_test == 400
    assert set(r.bundle.clases) == {"L", "V"}


def test_futbol_tiene_tres_clases_y_empates() -> None:
    partidos, _ = generar_datos(Deporte.FUTBOL, partidos=400, seed=5)
    r = entrenar_resultado(Deporte.FUTBOL, partidos)
    assert set(r.bundle.clases) == set(CLASES_RESULTADO[Deporte.FUTBOL]) == {"L", "E", "V"}
    assert r.metrica < r.baseline


def test_nfl_descarta_empates() -> None:
    partidos, _ = generar_datos(Deporte.AMERICANO, partidos=200, seed=9)
    partidos.loc[partidos.index[0], "marcador_visita"] = partidos.loc[
        partidos.index[0], "marcador_local"
    ]
    empates = int((partidos["marcador_local"] == partidos["marcador_visita"]).sum())
    assert empates >= 1
    r = entrenar_resultado(Deporte.AMERICANO, partidos)
    assert set(r.bundle.clases) == {"L", "V"}
    assert r.n_train + r.n_test == len(partidos) - empates


def test_particion_temporal_no_parte_una_fecha() -> None:
    fechas = pd.Series(
        pd.to_datetime(["2025-01-01"] * 3 + ["2025-01-02"] * 3 + ["2025-01-03"] * 4, utc=True)
    )
    entrena, valida = particion_temporal(fechas)
    assert entrena.sum() + valida.sum() == len(fechas)
    assert not (set(fechas[entrena]) & set(fechas[valida]))
    assert valida.sum() > 0


def test_datos_insuficientes_con_pocos_partidos() -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=10)
    with pytest.raises(DatosInsuficientesError):
        entrenar_resultado(Deporte.BASQUETBOL, partidos)


def test_datos_insuficientes_sin_fechas_distintas() -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=80)
    partidos["fecha"] = partidos["fecha"].iloc[0]
    with pytest.raises(DatosInsuficientesError):
        entrenar_resultado(Deporte.BASQUETBOL, partidos)


def test_prediccion_produce_probabilidades_validas() -> None:
    partidos, _ = generar_datos(Deporte.FUTBOL, partidos=300, seed=2)
    r = entrenar_resultado(Deporte.FUTBOL, partidos)
    feats = features_partidos(partidos).tail(5)
    salida = predecir_resultado(r.bundle, feats)
    suma = salida[["prob_local", "prob_empate", "prob_visita"]].sum(axis=1)
    assert np.allclose(suma, 1.0)
    assert (salida["marcador_esperado_local"] >= 0).all()
    assert not salida.isna().any().any()


def test_prediccion_basquetbol_sin_empates_tiene_probabilidad_cero() -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=120, seed=4)
    r = entrenar_resultado(Deporte.BASQUETBOL, partidos)
    salida = predecir_resultado(r.bundle, features_partidos(partidos).tail(3))
    assert (salida["prob_empate"] == 0.0).all()
    assert math.isclose(float(salida["prob_local"].iloc[0] + salida["prob_visita"].iloc[0]), 1.0)
