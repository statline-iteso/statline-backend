"""NFL through api-american-football (league 1).

Field names and the status codes below come from the API-Sports documentation, not from a live
response (no API key in development). Confirm them against a real payload before relying on the
NFL metrics; see docs/DECISIONS.md.

Player lines arrive grouped by category (Passing, Rushing, Receiving, Defensive, Kicking) with
string values such as "24/35" (made/attempts), "1-2" or "-". Missing, "-" or unparsable values
count as 0, and a player without any recognised group is skipped, like a DNP in basketball.
"""

import math
import re
from datetime import date, datetime
from typing import Any

from ingesta.adaptadores.api_sports import ClienteApiSports
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.modelos import (
    Deporte,
    EquipoNorm,
    EstadisticaNorm,
    EstatusPartido,
    JugadorNorm,
    PartidoNorm,
)

NFL_LEAGUE_ID = "1"

# american-football status.short → EstatusPartido
_ESTATUS = {
    "NS": EstatusPartido.PROGRAMADO,
    "Q1": EstatusPartido.EN_JUEGO,
    "Q2": EstatusPartido.EN_JUEGO,
    "Q3": EstatusPartido.EN_JUEGO,
    "Q4": EstatusPartido.EN_JUEGO,
    "OT": EstatusPartido.EN_JUEGO,
    "HT": EstatusPartido.EN_JUEGO,
    "BT": EstatusPartido.EN_JUEGO,
    "INT": EstatusPartido.EN_JUEGO,
    "FT": EstatusPartido.FINALIZADO,
    "AOT": EstatusPartido.FINALIZADO,
    "AWD": EstatusPartido.FINALIZADO,
    "WO": EstatusPartido.FINALIZADO,
    "PST": EstatusPartido.POSPUESTO,
    "POST": EstatusPartido.POSPUESTO,
    "SUSP": EstatusPartido.POSPUESTO,
    "CANC": EstatusPartido.CANCELADO,
    "ABD": EstatusPartido.CANCELADO,
}

# Category names as API-Sports spells them (lowercased before lookup), first match wins.
_GRUPO_PASE = ("passing",)
_GRUPO_CARRERA = ("rushing",)
_GRUPO_RECEPCION = ("receiving",)
_GRUPO_DEFENSA = ("defensive", "defense")
_GRUPO_PATEO = ("kicking",)

_PAR = re.compile(r"^\s*(\d+)\s*[/-]\s*(\d+)\s*$")

Estadisticas = dict[str, Any]  # stat name (lowercased) → raw value


class AdaptadorAmericano(AdaptadorDeporte):
    deporte = Deporte.AMERICANO
    proveedor = "api-sports"
    proveedor_liga_id = NFL_LEAGUE_ID

    def __init__(self, cliente: ClienteApiSports, temporada: str) -> None:
        self._cliente = cliente
        self._temporada = temporada

    def peticiones_usadas(self) -> int:
        return self._cliente.peticiones

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        return self._cliente.get(
            "/games",
            {"league": NFL_LEAGUE_ID, "season": self._temporada, "date": fecha.isoformat()},
        )

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        return self._cliente.get("/games/statistics/players", {"id": partido_proveedor_id})

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        resultado: list[PartidoNorm] = []
        for p in partidos:
            local, visita = p["teams"]["home"], p["teams"]["away"]
            scores = p.get("scores") or {}
            resultado.append(
                PartidoNorm(
                    proveedor_id=str(p["id"]),
                    fecha=datetime.fromisoformat(p["date"]),
                    temporada=str((p.get("league") or {}).get("season", self._temporada)),
                    estatus=_ESTATUS.get(p["status"]["short"], EstatusPartido.EN_JUEGO),
                    local=EquipoNorm(str(local["id"]), local["name"], logo_url=local.get("logo")),
                    visita=EquipoNorm(
                        str(visita["id"]), visita["name"], logo_url=visita.get("logo")
                    ),
                    # NFL "week" labels ("Week 10", "Pre Season 1") are not a clean jornada.
                    jornada=None,
                    marcador_local=_total(scores.get("home")),
                    marcador_visita=_total(scores.get("away")),
                )
            )
        return resultado

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        resultado: list[EstadisticaNorm] = []
        for linea in lineas:
            metricas = _metricas(_grupos(linea.get("groups")))
            if not metricas:
                # Did not play, or only reported categories this adapter does not map.
                continue
            jugador = linea["player"]
            resultado.append(
                EstadisticaNorm(
                    partido_proveedor_id=partido_proveedor_id,
                    equipo_proveedor_id=str(linea["team"]["id"]),
                    jugador=JugadorNorm(
                        str(jugador["id"]),
                        str(jugador["name"]),
                        posicion=str(jugador["position"]) if jugador.get("position") else None,
                    ),
                    # NFL box scores have no minutes; minutes are a column, not a metric.
                    minutos=None,
                    metricas=metricas,
                )
            )
        return resultado


def _total(bloque: Any) -> int | None:
    if not isinstance(bloque, dict) or bloque.get("total") is None:
        return None
    return int(_numero(bloque["total"]))


def _grupos(crudos: Any) -> dict[str, Estadisticas]:
    """[{name, statistics: [{name, value}]}] → {group: {stat: value}} with lowercased names."""
    grupos: dict[str, Estadisticas] = {}
    for grupo in crudos or []:
        stats = grupo.get("statistics") or []
        grupos[str(grupo["name"]).strip().lower()] = {
            str(s["name"]).strip().lower(): s.get("value") for s in stats
        }
    return grupos


def _grupo(grupos: dict[str, Estadisticas], nombres: tuple[str, ...]) -> Estadisticas | None:
    for nombre in nombres:
        if nombre in grupos:
            return grupos[nombre]
    return None


def _metricas(grupos: dict[str, Estadisticas]) -> dict[str, dict[str, float]]:
    """Maps API-Sports categories to schemas/americano.schema.json groups."""
    metricas: dict[str, dict[str, float]] = {}

    if (g := _grupo(grupos, _GRUPO_PASE)) is not None:
        completos, intentos = _par(g.get("completions/attempts"))
        metricas["pase"] = {
            "completos": completos,
            "intentos": intentos,
            "yardas": _entero(g.get("yards")),
            "touchdowns": _conteo(g.get("touchdowns")),
            "intercepciones": _conteo(g.get("interceptions")),
            "capturas": _conteo(g.get("sacks")),
        }
    if (g := _grupo(grupos, _GRUPO_CARRERA)) is not None:
        metricas["carrera"] = {
            "acarreos": _conteo(g.get("carries")),
            "yardas": _entero(g.get("yards")),
            "touchdowns": _conteo(g.get("touchdowns")),
            "balonesSueltos": _conteo(g.get("fumbles lost")),
        }
    if (g := _grupo(grupos, _GRUPO_RECEPCION)) is not None:
        metricas["recepcion"] = {
            "objetivos": _conteo(g.get("targets")),
            "recepciones": _conteo(g.get("receptions")),
            "yardas": _entero(g.get("yards")),
            "touchdowns": _conteo(g.get("touchdowns")),
        }
    if (g := _grupo(grupos, _GRUPO_DEFENSA)) is not None:
        metricas["defensa"] = {
            "tacleadas": _conteo(g.get("tackles")),
            "capturas": _decimal(g.get("sacks")),
            "intercepciones": _conteo(g.get("interceptions")),
            "pasesDefendidos": _conteo(g.get("passes defended")),
            "balonesForzados": _conteo(g.get("forced fumbles")),
        }
    if (g := _grupo(grupos, _GRUPO_PATEO)) is not None:
        fg_anotados, fg_intentados = _par(g.get("field goals"))
        xp_anotados, xp_intentados = _par(g.get("extra points"))
        metricas["pateo"] = {
            "golesCampoAnotados": fg_anotados,
            "golesCampoIntentados": fg_intentados,
            "puntosExtraAnotados": xp_anotados,
            "puntosExtraIntentados": xp_intentados,
        }
    return metricas


def _numero(valor: Any) -> float:
    """Parses API-Sports numeric strings ("12", "1,250", "1.5"). Anything else counts as 0."""
    if isinstance(valor, bool):
        return 0.0
    if isinstance(valor, int | float):
        numero = float(valor)
    elif isinstance(valor, str):
        try:
            numero = float(valor.strip().replace(",", ""))
        except ValueError:
            return 0.0
    else:
        return 0.0
    return numero if math.isfinite(numero) else 0.0


def _entero(valor: Any) -> int:
    """Signed integer (yards can be negative)."""
    return int(_numero(valor))


def _conteo(valor: Any) -> int:
    """Non-negative count, as the schema requires."""
    return max(0, _entero(valor))


def _decimal(valor: Any) -> float:
    """Non-negative decimal (defensive sacks can be 1.5)."""
    return max(0.0, _numero(valor))


def _par(valor: Any) -> tuple[int, int]:
    """ "24/35" or "2-3" → (made, attempts). Anything else → (0, 0)."""
    if isinstance(valor, str):
        coincidencia = _PAR.match(valor)
        if coincidencia:
            return int(coincidencia.group(1)), int(coincidencia.group(2))
    return 0, 0
