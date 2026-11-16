import pytest

from ingesta.modelos import Deporte
from ingesta.validacion import MetricasInvalidasError, validar_metricas


@pytest.mark.parametrize(
    ("deporte", "metricas"),
    [
        (Deporte.BASQUETBOL, {"puntos": 30, "rebotes": 10, "asistencias": 8, "masMenos": -4}),
        (
            Deporte.AMERICANO,
            {"pase": {"completos": 22, "intentos": 31, "yardas": 280, "touchdowns": 2}},
        ),
        (Deporte.AMERICANO, {"carrera": {"acarreos": 18, "yardas": -3}}),
        (Deporte.FUTBOL, {"goles": 1, "asistencias": 0, "precisionPases": 87.5}),
    ],
)
def test_metricas_validas(schemas_dir: str, deporte: Deporte, metricas: dict[str, object]) -> None:
    validar_metricas(schemas_dir, deporte, metricas)


@pytest.mark.parametrize(
    ("deporte", "metricas", "mensaje"),
    [
        (Deporte.BASQUETBOL, {"puntos": 30, "rebotes": 10}, "asistencias"),
        (Deporte.BASQUETBOL, {"puntos": -1, "rebotes": 0, "asistencias": 0}, "puntos"),
        (Deporte.BASQUETBOL, {"puntos": 1, "rebotes": 0, "asistencias": 0, "goles": 1}, "goles"),
        (Deporte.AMERICANO, {}, "raíz"),
        (Deporte.AMERICANO, {"pase": {"completos": 1}}, "pase"),
        (Deporte.FUTBOL, {"goles": 0, "asistencias": 0, "tarjetasRojas": 2}, "tarjetasRojas"),
    ],
)
def test_metricas_invalidas(
    schemas_dir: str, deporte: Deporte, metricas: dict[str, object], mensaje: str
) -> None:
    with pytest.raises(MetricasInvalidasError, match=mensaje):
        validar_metricas(schemas_dir, deporte, metricas)
