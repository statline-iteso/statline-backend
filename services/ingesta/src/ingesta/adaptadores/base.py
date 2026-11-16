"""AdaptadorDeporte: the one interface every sport implements (proposal §3.3)."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from ingesta.modelos import Deporte, EstadisticaNorm, PartidoNorm


class AdaptadorDeporte(ABC):
    """Fetches raw provider data for one sport and turns it into normalized records.

    `obtener_*` do I/O and return the provider payload untouched; `normalizar*` are pure, so they
    can be tested with recorded fixtures and no network.
    """

    deporte: Deporte
    proveedor: str
    proveedor_liga_id: str

    def peticiones_usadas(self) -> int:
        """Provider requests made so far in this run (recorded in ejecucion_ingesta)."""
        return 0

    @abstractmethod
    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        """Raw games for one day."""

    @abstractmethod
    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        """Raw player box-score lines for one finished game."""

    @abstractmethod
    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        """Raw games → PartidoNorm."""

    @abstractmethod
    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        """Raw box-score lines → EstadisticaNorm with sport-specific `metricas`."""
