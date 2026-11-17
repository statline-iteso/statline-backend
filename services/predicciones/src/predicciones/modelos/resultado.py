"""Match outcome model (SL-34): multinomial logistic regression plus two Poisson score models.

Classes: L/V for NBA and NFL (ties are dropped, they cannot be a class there), L/E/V for futbol.
Baseline: the training class priors. Metric: log-loss on the last 20 % of games by date.
The bundle is fitted on the training part only, so the reported metric describes the artifact.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from predicciones.deportes import CLASES_RESULTADO, VENTANA_DEFAULT, clase_resultado
from predicciones.errores import DatosInsuficientesError
from predicciones.features import features_partidos
from predicciones.modelos.base import ResultadoEntrenamiento, particion_temporal
from predicciones.schemas import Deporte, TipoInferencia

MIN_PARTIDOS_RESULTADO = 60
MAX_ITER = 1000

_ETIQUETA_PROB = {"L": "prob_local", "E": "prob_empate", "V": "prob_visita"}


@dataclass(frozen=True)
class BundleResultado:
    deporte: Deporte
    clasificador: Any  # Pipeline: imputer -> scaler -> LogisticRegression
    goles_local: Any  # Pipeline: imputer -> scaler -> PoissonRegressor
    goles_visita: Any
    features: tuple[str, ...]
    clases: tuple[str, ...]


def _pipeline_clase() -> Pipeline:
    return Pipeline(
        [
            ("imputar", SimpleImputer(strategy="mean")),
            ("escalar", StandardScaler()),
            ("clasificar", LogisticRegression(max_iter=MAX_ITER)),
        ]
    )


def _pipeline_goles() -> Pipeline:
    return Pipeline(
        [
            ("imputar", SimpleImputer(strategy="mean")),
            ("escalar", StandardScaler()),
            ("goles", PoissonRegressor(alpha=1.0, max_iter=MAX_ITER)),
        ]
    )


def entrenar_resultado(
    deporte: Deporte,
    partidos: pd.DataFrame,
    *,
    ventana: int = VENTANA_DEFAULT,
) -> ResultadoEntrenamiento:
    """Train and validate the outcome model on finished games (see datos.cargar_partidos).

    Raises DatosInsuficientesError when there are too few usable games, when a class is missing
    from the training part, or when the holdout is empty.
    """
    terminados = partidos.dropna(subset=["marcador_local", "marcador_visita"]).copy()
    terminados["clase"] = [
        clase_resultado(deporte, ml, mv)
        for ml, mv in zip(terminados["marcador_local"], terminados["marcador_visita"], strict=True)
    ]
    usables = terminados.dropna(subset=["clase"]).sort_values("fecha").reset_index(drop=True)
    if len(usables) < MIN_PARTIDOS_RESULTADO:
        raise DatosInsuficientesError(
            f"{deporte.value}: {len(usables)} partidos utilizables, se requieren "
            f"al menos {MIN_PARTIDOS_RESULTADO}"
        )
    x_todas = features_partidos(terminados, ventana=ventana).loc[usables["partido_id"]]
    x_todas = x_todas.reset_index(drop=True)
    entrenamiento, validacion = particion_temporal(usables["fecha"])
    clases = CLASES_RESULTADO[deporte]
    y_train = usables.loc[entrenamiento, "clase"]
    y_test = usables.loc[validacion, "clase"]
    if set(y_train.unique()) != set(clases):
        raise DatosInsuficientesError(
            f"{deporte.value}: el entrenamiento no tiene todas las clases {clases}"
        )
    if y_test.empty:
        raise DatosInsuficientesError(f"{deporte.value}: el conjunto de validación está vacío")

    x_train = x_todas[entrenamiento.to_numpy()]
    x_test = x_todas[validacion.to_numpy()]
    clasificador = _pipeline_clase().fit(x_train, y_train)
    etiquetas = list(clasificador.classes_)
    metrica = float(log_loss(y_test, clasificador.predict_proba(x_test), labels=etiquetas))

    priores = y_train.value_counts(normalize=True).reindex(etiquetas).to_numpy(dtype=float)
    baseline = float(log_loss(y_test, np.tile(priores, (len(y_test), 1)), labels=etiquetas))

    goles_local = _pipeline_goles().fit(x_train, usables.loc[entrenamiento, "marcador_local"])
    goles_visita = _pipeline_goles().fit(x_train, usables.loc[entrenamiento, "marcador_visita"])
    bundle = BundleResultado(
        deporte=deporte,
        clasificador=clasificador,
        goles_local=goles_local,
        goles_visita=goles_visita,
        features=tuple(x_todas.columns),
        clases=tuple(etiquetas),
    )
    return ResultadoEntrenamiento(
        deporte=deporte,
        tipo=TipoInferencia.RESULTADO_PARTIDO,
        bundle=bundle,
        nombre_metrica="log_loss",
        metrica=metrica,
        baseline=baseline,
        n_train=int(entrenamiento.sum()),
        n_test=int(validacion.sum()),
        features=bundle.features,
    )


def predecir_resultado(bundle: BundleResultado, features: pd.DataFrame) -> pd.DataFrame:
    """Probabilities (prob_local, prob_empate, prob_visita; 0 when a sport has no draws) and
    expected scores, aligned to the index of `features`."""
    x = features.loc[:, list(bundle.features)]
    proba = bundle.clasificador.predict_proba(x)
    salida = pd.DataFrame(index=features.index)
    for etiqueta in ("prob_local", "prob_empate", "prob_visita"):
        salida[etiqueta] = 0.0
    for columna, clase in enumerate(bundle.clasificador.classes_):
        salida[_ETIQUETA_PROB[str(clase)]] = proba[:, columna]
    salida["marcador_esperado_local"] = bundle.goles_local.predict(x)
    salida["marcador_esperado_visita"] = bundle.goles_visita.predict(x)
    return salida
