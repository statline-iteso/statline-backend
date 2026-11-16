"""Contract between the Node API and this service (docs/ARCHITECTURE.md §7)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Deporte(StrEnum):
    BASQUETBOL = "BASQUETBOL"
    AMERICANO = "AMERICANO"
    FUTBOL = "FUTBOL"


class TipoInferencia(StrEnum):
    RESULTADO_PARTIDO = "RESULTADO_PARTIDO"
    PROYECCION_JUGADOR = "PROYECCION_JUGADOR"


class GenerarPronosticosRequest(BaseModel):
    deporte: Deporte
    jornada: int | None = Field(default=None, ge=1)
    partido_ids: list[str] = Field(default_factory=list, max_length=200)


class GenerarProyeccionesRequest(BaseModel):
    deporte: Deporte
    jornada: int | None = Field(default=None, ge=1)
    jugador_ids: list[str] = Field(default_factory=list, max_length=500)


class ReentrenarRequest(BaseModel):
    deporte: Deporte
    tipo: TipoInferencia
