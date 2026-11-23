"""Shared pieces of the models: the training result and the time-based holdout."""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from predicciones.errores import DatosInsuficientesError
from predicciones.schemas import Deporte, TipoInferencia

FRACCION_TEST = 0.8  # the first 80 % of dates train, the last 20 % validate (D-30)


@dataclass(frozen=True)
class ResultadoEntrenamiento:
    """What a training run returns. Lower metric is better (log-loss, MAE)."""

    deporte: Deporte
    tipo: TipoInferencia
    bundle: Any
    nombre_metrica: str
    metrica: float
    baseline: float
    n_train: int
    n_test: int
    features: tuple[str, ...]
    detalle: dict[str, float] = field(default_factory=dict)

    @property
    def supera_baseline(self) -> bool:
        return self.metrica < self.baseline


def particion_temporal(fechas: pd.Series, fraccion: float = FRACCION_TEST) -> tuple[Any, Any]:
    """Boolean masks (train, test) by date: test holds the last rows after the cut date.

    The cut falls between dates, so every row of one game lands on the same side.
    """
    fechas_unicas = sorted(pd.unique(fechas))
    if len(fechas_unicas) < 2:
        raise DatosInsuficientesError("hacen falta al menos dos fechas distintas")
    indice = min(max(1, int(len(fechas_unicas) * fraccion)), len(fechas_unicas) - 1)
    corte = fechas_unicas[indice]
    return fechas < corte, fechas >= corte
