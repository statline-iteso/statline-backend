"""Player projection model (SL-35): one GradientBoostingRegressor per target metric.

Targets per sport come from OBJETIVOS_JUGADOR (real schema keys). Baseline: the player's rolling
average of the metric over his last games (the training mean when he has no history). Metric:
mean absolute error on the last 20 % of lines by date, averaged over the targets. Per-target MAE
goes to `detalle`. Targets a player does not record (NFL groups) are skipped per row.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from predicciones.deportes import OBJETIVOS_JUGADOR, VENTANA_DEFAULT
from predicciones.errores import DatosInsuficientesError
from predicciones.features import features_jugadores
from predicciones.modelos.base import ResultadoEntrenamiento, particion_temporal
from predicciones.schemas import Deporte, TipoInferencia

MIN_LINEAS_JUGADOR = 200
MIN_FILAS_OBJETIVO = 50
ESTIMADORES_DEFAULT = 200
SEMILLA = 42


@dataclass(frozen=True)
class BundleJugador:
    deporte: Deporte
    objetivos: tuple[str, ...]
    modelos: dict[str, Any]  # objetivo -> Pipeline(imputer, GradientBoostingRegressor)
    features: tuple[str, ...]
    ventana: int = VENTANA_DEFAULT  # games of history per player: inference must use the same


def _pipeline_objetivo(estimadores: int) -> Pipeline:
    return Pipeline(
        [
            ("imputar", SimpleImputer(strategy="median", keep_empty_features=True)),
            (
                "gbr",
                GradientBoostingRegressor(
                    n_estimators=estimadores,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.8,
                    random_state=SEMILLA,
                ),
            ),
        ]
    )


def entrenar_jugador(
    deporte: Deporte,
    lineas: pd.DataFrame,
    *,
    ventana: int = VENTANA_DEFAULT,
    estimadores: int = ESTIMADORES_DEFAULT,
) -> ResultadoEntrenamiento:
    """Train and validate the player models on finished lines (see datos.cargar_lineas)."""
    if len(lineas) < MIN_LINEAS_JUGADOR:
        raise DatosInsuficientesError(
            f"{deporte.value}: {len(lineas)} líneas de jugador, se requieren al menos "
            f"{MIN_LINEAS_JUGADOR}"
        )
    objetivos = OBJETIVOS_JUGADOR[deporte]
    faltantes = [o for o in objetivos if o not in lineas.columns]
    if faltantes:
        raise DatosInsuficientesError(f"faltan métricas en los datos: {faltantes}")

    features = features_jugadores(lineas, lineas, objetivos, ventana=ventana)
    entrenamiento, validacion = particion_temporal(lineas["fecha"])

    modelos: dict[str, Any] = {}
    detalle: dict[str, float] = {}
    maes: list[float] = []
    baselines: list[float] = []
    for objetivo in objetivos:
        y = lineas[objetivo].astype(float)
        con_dato = y.notna()
        mascara_train = entrenamiento & con_dato
        mascara_test = validacion & con_dato
        if mascara_train.sum() < MIN_FILAS_OBJETIVO or mascara_test.sum() == 0:
            raise DatosInsuficientesError(
                f"{deporte.value}/{objetivo}: filas insuficientes para entrenar y validar"
            )
        media = float(y[mascara_train].mean())
        prediccion_base = features.loc[mascara_test, f"prom_{objetivo}"].fillna(media)
        baseline = float(mean_absolute_error(y[mascara_test], prediccion_base))

        modelo = _pipeline_objetivo(estimadores).fit(features.loc[mascara_train], y[mascara_train])
        mae = float(
            mean_absolute_error(y[mascara_test], modelo.predict(features.loc[mascara_test]))
        )
        modelos[objetivo] = modelo
        detalle[f"mae_{objetivo}"] = mae
        detalle[f"baseline_mae_{objetivo}"] = baseline
        maes.append(mae)
        baselines.append(baseline)

    bundle = BundleJugador(
        deporte=deporte,
        objetivos=objetivos,
        modelos=modelos,
        features=tuple(features.columns),
        ventana=ventana,
    )
    return ResultadoEntrenamiento(
        deporte=deporte,
        tipo=TipoInferencia.PROYECCION_JUGADOR,
        bundle=bundle,
        nombre_metrica="mae",
        metrica=sum(maes) / len(maes),
        baseline=sum(baselines) / len(baselines),
        n_train=int(entrenamiento.sum()),
        n_test=int(validacion.sum()),
        features=bundle.features,
        detalle=detalle,
    )


def predecir_jugador(bundle: BundleJugador, features: pd.DataFrame) -> pd.DataFrame:
    """One column per objetivo with the projected value, aligned to `features`."""
    x = features.loc[:, list(bundle.features)]
    salida = pd.DataFrame(index=features.index)
    for objetivo in bundle.objetivos:
        salida[objetivo] = bundle.modelos[objetivo].predict(x)
    return salida
