"""NBA through balldontlie.io API v1: fallback when API-Sports is unavailable (SL-20, D-17).

Built from the balldontlie documentation, not from a live response. `/games?dates[]=` lists a day,
`/stats?game_ids[]=` returns the player lines of one game (cursor pagination on `meta.next_cursor`).
Output mirrors AdaptadorBasquetbol: same metric keys, DNPs dropped, ids namespaced `balldontlie:`.
"""

import re
from datetime import UTC, date, datetime, time
from typing import Any

from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.adaptadores.respaldo import (
    ClienteRespaldo,
    paginar_cursor,
    prefijar,
    quitar_prefijo,
)
from ingesta.modelos import (
    Deporte,
    EquipoNorm,
    EstadisticaNorm,
    EstatusPartido,
    JugadorNorm,
    PartidoNorm,
)

BASE_URL = "https://api.balldontlie.io/v1"
PROVEEDOR = "balldontlie"

# balldontlie stat field → key in schemas/basquetbol.schema.json
_METRICAS = {
    "pts": "puntos",
    "reb": "rebotes",
    "oreb": "rebotesOfensivos",
    "dreb": "rebotesDefensivos",
    "ast": "asistencias",
    "stl": "robos",
    "blk": "bloqueos",
    "turnover": "perdidas",
    "pf": "faltas",
    "fgm": "tirosCampoAnotados",
    "fga": "tirosCampoIntentados",
    "fg3m": "triplesAnotados",
    "fg3a": "triplesIntentados",
    "ftm": "tirosLibresAnotados",
    "fta": "tirosLibresIntentados",
    "plus_minus": "masMenos",
}
_HORA = re.compile(r"^\d{1,2}:\d{2}")  # tip-off time, e.g. "7:30 pm ET"
# Required by the schema: a missing value is stored as 0 (as in AdaptadorBasquetbol).
_REQUERIDAS = ("puntos", "rebotes", "asistencias")


class AdaptadorBalldontlie(AdaptadorDeporte):
    deporte = Deporte.BASQUETBOL
    proveedor = PROVEEDOR
    # Not a real league id here: the ejecutor writes into the API-Sports league row (see D-17).
    proveedor_liga_id = "NBA"

    def __init__(self, cliente: ClienteRespaldo, temporada: str) -> None:
        self._cliente = cliente
        self._temporada = temporada

    def peticiones_usadas(self) -> int:
        return self._cliente.peticiones

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        return paginar_cursor(self._cliente, "/games", {"dates[]": fecha.isoformat()})

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        crudo = quitar_prefijo(PROVEEDOR, partido_proveedor_id)
        return paginar_cursor(self._cliente, "/stats", {"game_ids[]": crudo})

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        resultado: list[PartidoNorm] = []
        for p in partidos:
            estatus = _estatus(p.get("status"))
            # Scheduled games come with 0-0 scores: store them only once the game has started.
            con_marcador = estatus is not EstatusPartido.PROGRAMADO
            resultado.append(
                PartidoNorm(
                    proveedor_id=prefijar(PROVEEDOR, p["id"]),
                    fecha=_fecha(p),
                    temporada=self._temporada,
                    estatus=estatus,
                    local=_equipo(p["home_team"]),
                    visita=_equipo(p["visitor_team"]),
                    marcador_local=_entero(p.get("home_team_score")) if con_marcador else None,
                    marcador_visita=_entero(p.get("visitor_team_score")) if con_marcador else None,
                )
            )
        return resultado

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        resultado: list[EstadisticaNorm] = []
        for linea in lineas:
            minutos = _minutos(linea.get("min"))
            # Players who did not play come with no minutes: drop them, as AdaptadorBasquetbol does.
            if minutos is None:
                continue
            jugador = linea["player"]
            metricas: dict[str, Any] = {}
            for origen, destino in _METRICAS.items():
                valor = _entero(linea.get(origen))
                if valor is None:
                    continue
                metricas[destino] = valor if destino == "masMenos" else max(valor, 0)
            for requerida in _REQUERIDAS:
                metricas.setdefault(requerida, 0)
            resultado.append(
                EstadisticaNorm(
                    partido_proveedor_id=partido_proveedor_id,
                    equipo_proveedor_id=prefijar(PROVEEDOR, linea["team"]["id"]),
                    jugador=JugadorNorm(
                        prefijar(PROVEEDOR, jugador["id"]),
                        f"{jugador.get('first_name', '')} {jugador.get('last_name', '')}".strip(),
                    ),
                    minutos=minutos,
                    metricas=metricas,
                )
            )
        return resultado


def _equipo(equipo: dict[str, Any]) -> EquipoNorm:
    return EquipoNorm(
        prefijar(PROVEEDOR, equipo["id"]),
        str(equipo["full_name"]),
        abreviatura=equipo.get("abbreviation"),
    )


def _fecha(partido: dict[str, Any]) -> datetime:
    """`datetime` is ISO 8601 UTC ("2026-11-14T00:30:00.000Z"); fall back to the day at midnight."""
    if partido.get("datetime"):
        return datetime.fromisoformat(str(partido["datetime"])).astimezone(UTC)
    return datetime.combine(date.fromisoformat(partido["date"]), time(0), tzinfo=UTC)


def _estatus(estado: object) -> EstatusPartido:
    """balldontlie `status`: "Scheduled", a tip-off time, "Final", "Final/OT" or "3rd Qtr"."""
    texto = str(estado or "").strip().lower()
    if texto.startswith("final"):
        return EstatusPartido.FINALIZADO
    if texto.startswith("postpon"):
        return EstatusPartido.POSPUESTO
    if texto.startswith("cancel"):
        return EstatusPartido.CANCELADO
    if texto in ("", "scheduled") or _HORA.match(texto):
        return EstatusPartido.PROGRAMADO
    return EstatusPartido.EN_JUEGO


def _minutos(valor: object) -> int | None:
    """ "36:12" or "36" → 36. Blank or missing means the player did not play."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    return _entero(texto.split(":", 1)[0])


def _entero(valor: object) -> int | None:
    """Stat values are ints, sometimes floats or numeric strings, sometimes null."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    try:
        return int(float(str(valor).strip()))
    except ValueError:
        return None
