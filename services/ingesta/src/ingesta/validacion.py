"""Strict validation of `metricas` against schemas/<deporte>.schema.json before any insert."""

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ingesta.modelos import Deporte


class MetricasInvalidasError(ValueError):
    pass


@cache
def _validador(schemas_dir: str, deporte: Deporte) -> Draft202012Validator:
    ruta = Path(schemas_dir) / f"{deporte.value.lower()}.schema.json"
    esquema = json.loads(ruta.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema)


def validar_metricas(schemas_dir: str, deporte: Deporte, metricas: dict[str, Any]) -> None:
    errores = sorted(_validador(schemas_dir, deporte).iter_errors(metricas), key=str)
    if errores:
        detalle = "; ".join(
            f"{'/'.join(map(str, e.path)) or '<raíz>'}: {e.message}" for e in errores
        )
        raise MetricasInvalidasError(f"{deporte}: {detalle}")
