"""NFL (league 4391) and Liga MX (league 4350) through TheSportsDB v1: fallback (SL-20, D-17).

Built from the TheSportsDB documentation, not from a live response. `eventsday.php?d=&l=` lists the
events of one day. The free tier has no player box scores, so `obtener_estadisticas` makes no
request and returns nothing: after a switch to this fallback only games and scores are stored.
Ids are namespaced `thesportsdb:` (D-17). `strTime` is taken as UTC (to confirm on a live response).
"""

from datetime import UTC, date, datetime, time
from typing import Any

from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.adaptadores.respaldo import ClienteRespaldo, prefijar
from ingesta.modelos import Deporte, EquipoNorm, EstadisticaNorm, EstatusPartido, PartidoNorm

BASE_URL = "https://www.thesportsdb.com/api/v1/json"
PROVEEDOR = "thesportsdb"

LIGAS: dict[Deporte, str] = {Deporte.AMERICANO: "4391", Deporte.FUTBOL: "4350"}

# TheSportsDB strStatus → EstatusPartido (free-text; unknown values count as in progress)
_ESTATUS = {
    "match finished": EstatusPartido.FINALIZADO,
    "ft": EstatusPartido.FINALIZADO,
    "aet": EstatusPartido.FINALIZADO,
    "ap": EstatusPartido.FINALIZADO,
    "not started": EstatusPartido.PROGRAMADO,
    "ns": EstatusPartido.PROGRAMADO,
    "tbd": EstatusPartido.PROGRAMADO,
    "postponed": EstatusPartido.POSPUESTO,
    "pst": EstatusPartido.POSPUESTO,
    "cancelled": EstatusPartido.CANCELADO,
    "canceled": EstatusPartido.CANCELADO,
    "canc": EstatusPartido.CANCELADO,
}


class AdaptadorTheSportsDB(AdaptadorDeporte):
    proveedor = PROVEEDOR

    def __init__(self, cliente: ClienteRespaldo, deporte: Deporte, temporada: str) -> None:
        self._cliente = cliente
        self._temporada = temporada
        self.deporte = deporte
        # Not used for the write (the ejecutor keeps the primary league row, see D-17).
        self.proveedor_liga_id = LIGAS[deporte]

    def peticiones_usadas(self) -> int:
        return self._cliente.peticiones

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        cuerpo = self._cliente.get(
            "/eventsday.php", {"d": fecha.isoformat(), "l": self.proveedor_liga_id}
        )
        # TheSportsDB answers {"events": null} for a day without games.
        return list(cuerpo.get("events") or [])

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        del partido_proveedor_id  # no box scores on the free tier; no request is made
        return []

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        resultado: list[PartidoNorm] = []
        for e in partidos:
            estatus = _ESTATUS.get(str(e.get("strStatus") or "").strip().lower())
            estatus = estatus or EstatusPartido.EN_JUEGO
            con_marcador = estatus is not EstatusPartido.PROGRAMADO
            resultado.append(
                PartidoNorm(
                    proveedor_id=prefijar(PROVEEDOR, e["idEvent"]),
                    fecha=_fecha(e),
                    temporada=str(e.get("strSeason") or self._temporada),
                    estatus=estatus,
                    local=_equipo(e, "Home"),
                    visita=_equipo(e, "Away"),
                    jornada=_entero(e.get("intRound")),
                    marcador_local=_entero(e.get("intHomeScore")) if con_marcador else None,
                    marcador_visita=_entero(e.get("intAwayScore")) if con_marcador else None,
                )
            )
        return resultado

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        del partido_proveedor_id, lineas  # always empty: see obtener_estadisticas
        return []


def _equipo(evento: dict[str, Any], lado: str) -> EquipoNorm:
    return EquipoNorm(
        prefijar(PROVEEDOR, evento[f"id{lado}Team"]),
        str(evento[f"str{lado}Team"]),
        logo_url=evento.get(f"str{lado}TeamBadge") or None,
    )


def _fecha(evento: dict[str, Any]) -> datetime:
    """dateEvent "2026-11-14" + strTime "00:30:00" (UTC); missing time → midnight."""
    dia = date.fromisoformat(str(evento["dateEvent"]))
    hora = time.fromisoformat(str(evento.get("strTime") or "00:00:00"))
    return datetime.combine(dia, hora, tzinfo=UTC)


def _entero(valor: object) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(str(valor).strip())
    except ValueError:
        return None
