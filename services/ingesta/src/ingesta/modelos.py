"""Normalized records: what every adapter produces, regardless of sport or provider."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Deporte(StrEnum):
    BASQUETBOL = "BASQUETBOL"
    AMERICANO = "AMERICANO"
    FUTBOL = "FUTBOL"


class EstatusPartido(StrEnum):
    PROGRAMADO = "PROGRAMADO"
    EN_JUEGO = "EN_JUEGO"
    FINALIZADO = "FINALIZADO"
    POSPUESTO = "POSPUESTO"
    CANCELADO = "CANCELADO"


@dataclass(frozen=True)
class EquipoNorm:
    proveedor_id: str
    nombre: str
    abreviatura: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True)
class PartidoNorm:
    proveedor_id: str
    fecha: datetime
    temporada: str
    estatus: EstatusPartido
    local: EquipoNorm
    visita: EquipoNorm
    jornada: int | None = None
    marcador_local: int | None = None
    marcador_visita: int | None = None


@dataclass(frozen=True)
class JugadorNorm:
    proveedor_id: str
    nombre: str
    posicion: str | None = None


@dataclass(frozen=True)
class EstadisticaNorm:
    """One box-score line. `metricas` must validate against schemas/<deporte>.schema.json."""

    partido_proveedor_id: str
    equipo_proveedor_id: str
    jugador: JugadorNorm
    minutos: int | None
    metricas: dict[str, Any] = field(default_factory=dict)
