"""Per-sport modelling choices: outcome classes and player target metrics.

Metric keys are the ones in schemas/*.schema.json. NFL keys are nested groups, flattened with a
dot (`pase.yardas`), see datos.aplanar_metricas.
"""

from predicciones.schemas import Deporte

CLASE_LOCAL = "L"
CLASE_EMPATE = "E"
CLASE_VISITA = "V"

CLASES_RESULTADO: dict[Deporte, tuple[str, ...]] = {
    Deporte.BASQUETBOL: (CLASE_LOCAL, CLASE_VISITA),
    Deporte.AMERICANO: (CLASE_LOCAL, CLASE_VISITA),
    Deporte.FUTBOL: (CLASE_LOCAL, CLASE_EMPATE, CLASE_VISITA),
}

OBJETIVOS_JUGADOR: dict[Deporte, tuple[str, ...]] = {
    Deporte.BASQUETBOL: ("puntos", "rebotes", "asistencias"),
    Deporte.AMERICANO: ("pase.yardas", "carrera.yardas", "recepcion.yardas"),
    Deporte.FUTBOL: ("goles", "asistencias", "tiros"),
}

VENTANA_DEFAULT = 10


def clase_resultado(deporte: Deporte, marcador_local: float, marcador_visita: float) -> str | None:
    """Outcome class of a finished game, or None when it is dropped (a tie in NBA/NFL)."""
    if marcador_local > marcador_visita:
        return CLASE_LOCAL
    if marcador_local < marcador_visita:
        return CLASE_VISITA
    return CLASE_EMPATE if Deporte.FUTBOL is deporte else None
