import pytest
from fabrica import generar_datos

from predicciones.deportes import OBJETIVOS_JUGADOR
from predicciones.errores import DatosInsuficientesError
from predicciones.features import features_jugadores
from predicciones.modelos.jugador import entrenar_jugador, predecir_jugador
from predicciones.schemas import Deporte, TipoInferencia


@pytest.mark.parametrize("deporte", [Deporte.BASQUETBOL, Deporte.AMERICANO, Deporte.FUTBOL])
def test_un_modelo_por_objetivo_y_metricas_por_objetivo(deporte: Deporte) -> None:
    _, lineas = generar_datos(deporte, partidos=260, seed=11)
    r = entrenar_jugador(deporte, lineas, estimadores=40)
    assert r.tipo is TipoInferencia.PROYECCION_JUGADOR
    assert r.nombre_metrica == "mae"
    assert set(r.bundle.modelos) == set(OBJETIVOS_JUGADOR[deporte])
    for objetivo in OBJETIVOS_JUGADOR[deporte]:
        assert f"mae_{objetivo}" in r.detalle
        assert f"baseline_mae_{objetivo}" in r.detalle
    maes = [r.detalle[f"mae_{o}"] for o in OBJETIVOS_JUGADOR[deporte]]
    assert r.metrica == pytest.approx(sum(maes) / len(maes))


def test_basquetbol_supera_al_baseline_de_promedio_movil() -> None:
    _, lineas = generar_datos(Deporte.BASQUETBOL, partidos=400, seed=21)
    r = entrenar_jugador(Deporte.BASQUETBOL, lineas, estimadores=60)
    assert r.supera_baseline, (r.metrica, r.baseline, r.detalle)


def test_prediccion_tiene_una_columna_por_objetivo() -> None:
    _, lineas = generar_datos(Deporte.FUTBOL, partidos=260, seed=13)
    r = entrenar_jugador(Deporte.FUTBOL, lineas, estimadores=30)
    feats = features_jugadores(lineas, lineas, OBJETIVOS_JUGADOR[Deporte.FUTBOL]).tail(4)
    salida = predecir_jugador(r.bundle, feats)
    assert list(salida.columns) == list(OBJETIVOS_JUGADOR[Deporte.FUTBOL])
    assert not salida.isna().any().any()


def test_pocas_lineas_levanta_datos_insuficientes() -> None:
    _, lineas = generar_datos(Deporte.BASQUETBOL, partidos=10)
    with pytest.raises(DatosInsuficientesError):
        entrenar_jugador(Deporte.BASQUETBOL, lineas)


def test_falta_una_metrica_levanta_datos_insuficientes() -> None:
    _, lineas = generar_datos(Deporte.FUTBOL, partidos=260)
    with pytest.raises(DatosInsuficientesError):
        entrenar_jugador(Deporte.FUTBOL, lineas.drop(columns=["tiros"]), estimadores=5)


def test_objetivo_sin_filas_suficientes_levanta_error() -> None:
    _, lineas = generar_datos(Deporte.AMERICANO, partidos=260)
    lineas["pase.yardas"] = float("nan")
    with pytest.raises(DatosInsuficientesError):
        entrenar_jugador(Deporte.AMERICANO, lineas, estimadores=5)
