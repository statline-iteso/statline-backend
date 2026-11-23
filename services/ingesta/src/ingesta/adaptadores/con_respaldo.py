"""Primary adapter plus one fallback provider, for the rest of a run (SL-20, D-26).

The first provider failure that means "unavailable" (quota exhausted, retries exhausted on 5xx,
429 or network, or a request the key's plan does not cover) switches the run to the fallback for
every later call. The providers actually used
are kept in `proveedor_efectivo()` ("api-sports+balldontlie") and logged.

Games from the fallback carry namespaced ids, so their box scores are routed back to the fallback.
A game already fetched from the primary cannot be looked up in the fallback (different ids): its
box score is skipped with a warning and the game row is still stored.
"""

import logging
from datetime import date
from typing import Any

from ingesta.adaptadores.api_sports import (
    CuotaAgotadaError,
    PlanSinAccesoError,
    ProveedorCaidoError,
)
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.modelos import EstadisticaNorm, PartidoNorm

log = logging.getLogger(__name__)

_CAIDAS = (CuotaAgotadaError, ProveedorCaidoError, PlanSinAccesoError)
_SOLO_PLANTILLA = "AdaptadorConRespaldo usa partidos_del_dia y lineas_del_partido"


class AdaptadorConRespaldo(AdaptadorDeporte):
    def __init__(self, principal: AdaptadorDeporte, respaldo: AdaptadorDeporte) -> None:
        self.deporte = principal.deporte
        # Liga identity stays the primary's: the seeded `liga` row is keyed on api-sports.
        self.proveedor = principal.proveedor
        self.proveedor_liga_id = principal.proveedor_liga_id
        self._principal = principal
        self._respaldo = respaldo
        self._en_respaldo = False
        self._usados = [principal.proveedor]

    def peticiones_usadas(self) -> int:
        return self._principal.peticiones_usadas() + self._respaldo.peticiones_usadas()

    def proveedor_efectivo(self) -> str:
        return "+".join(self._usados)

    def partidos_del_dia(self, fecha: date) -> list[PartidoNorm]:
        if not self._en_respaldo:
            try:
                return self._principal.partidos_del_dia(fecha)
            except _CAIDAS as err:
                self._cambiar_a_respaldo(err)
        return self._respaldo.partidos_del_dia(fecha)

    def lineas_del_partido(self, partido_proveedor_id: str) -> list[EstadisticaNorm]:
        if partido_proveedor_id.startswith(f"{self._respaldo.proveedor}:"):
            return self._respaldo.lineas_del_partido(partido_proveedor_id)
        if self._en_respaldo:
            log.warning(
                "partido %s sin estadisticas: se obtuvo de %s",
                partido_proveedor_id,
                self._principal.proveedor,
            )
            return []
        try:
            return self._principal.lineas_del_partido(partido_proveedor_id)
        except _CAIDAS as err:
            self._cambiar_a_respaldo(err)
            log.warning(
                "partido %s sin estadisticas: %s no conoce sus ids",
                partido_proveedor_id,
                self._respaldo.proveedor,
            )
            return []

    def _cambiar_a_respaldo(self, motivo: Exception) -> None:
        if self._en_respaldo:
            return
        self._en_respaldo = True
        self._usados.append(self._respaldo.proveedor)
        log.warning(
            "proveedor %s no disponible (%s); se usa %s para el resto de la corrida",
            self._principal.proveedor,
            motivo,
            self._respaldo.proveedor,
        )

    # The raw payload differs per provider, so the run goes through the template methods above.
    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        raise NotImplementedError(_SOLO_PLANTILLA)

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError(_SOLO_PLANTILLA)

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        raise NotImplementedError(_SOLO_PLANTILLA)

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        raise NotImplementedError(_SOLO_PLANTILLA)
