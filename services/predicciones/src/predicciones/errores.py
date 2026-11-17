"""Domain errors. main.py maps them to HTTP codes (409, 422, 404, 500, 503)."""


class PrediccionesError(Exception):
    """Base class for domain errors raised by this package."""


class DatosInsuficientesError(PrediccionesError):
    """Not enough finished games or player lines to train or validate a model."""


class SinModeloActivoError(PrediccionesError):
    """No ModeloPrediccion is active for the requested (deporte, tipo)."""


class ModeloNoEncontradoError(PrediccionesError):
    """The ModeloPrediccion id does not exist."""


class ArtefactoInvalidoError(PrediccionesError):
    """Stored artifact bytes do not match the recorded sha256 (tampered or corrupt)."""


class BaseDatosNoDisponibleError(PrediccionesError):
    """PostgreSQL is not configured or cannot be reached (mapped to 503)."""
