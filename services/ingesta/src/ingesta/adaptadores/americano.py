"""NFL through api-american-football (league 1).

Field names and the status codes below come from the API-Sports documentation, not from a live
response (no API key in development). Confirm them against a real payload before relying on the
NFL metrics; see docs/DECISIONS.md.

Unlike api-basketball, games nest under `game` (id, status, date{date,time,timestamp}) and the
player statistics come per team: [{team, groups: [{name, players: [{player, statistics}]}]}].
They are regrouped per player here. Values are strings such as "24/35" (made/attempts), "1-2" or
"-"; missing, "-" or unparsable values count as 0, and a player without any recognised group is
skipped, like a DNP in basketball. The API does not report player positions.
"""

import math
import re
from datetime import UTC, date, datetime
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
            juego = p.get("game") or p
            local, visita = p["teams"]["home"], p["teams"]["away"]
            scores = p.get("scores") or {}
            resultado.append(
                PartidoNorm(
                    proveedor_id=str(juego["id"]),
                    fecha=_fecha(juego["date"]),
                    temporada=str((p.get("league") or {}).get("season", self._temporada)),
                    estatus=_ESTATUS.get(juego["status"]["short"], EstatusPartido.EN_JUEGO),
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
        for equipo, jugador, grupos in _jugadores(lineas):
            metricas = _metricas(grupos)
            if not metricas:
                # Did not play, or only reported categories this adapter does not map.
                continue
            resultado.append(
                EstadisticaNorm(
                    partido_proveedor_id=partido_proveedor_id,
                    equipo_proveedor_id=equipo,
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


def _fecha(valor: Any) -> datetime:
    """{date, time, timestamp} (UTC unless a timezone is requested) or an ISO string → aware."""
    if isinstance(valor, dict):
        if valor.get("timestamp") is not None:
            return datetime.fromtimestamp(int(valor["timestamp"]), tz=UTC)
        valor = f"{valor['date']}T{valor.get('time') or '00:00'}"
    fecha = datetime.fromisoformat(str(valor))
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)


def _jugadores(
    lineas: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any], dict[str, Estadisticas]]]:
    """Regroups [{team, groups[{name, players[{player, statistics}]}]}] by player.

    Also accepts one entry per player ({team, player, groups[{name, statistics}]}).
    """
    por_jugador: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Estadisticas]]] = {}
    for linea in lineas:
        equipo = str(linea["team"]["id"])
        if "player" in linea:
            entradas = [(linea["player"], g) for g in linea.get("groups") or []]
        else:
            entradas = [
                (j["player"], {"name": g["name"], "statistics": j.get("statistics")})
                for g in linea.get("groups") or []
                for j in g.get("players") or []
            ]
        for jugador, grupo in entradas:
            _, grupos = por_jugador.setdefault((equipo, str(jugador["id"])), (jugador, {}))
            grupos.update(_grupos([grupo]))
    return [(clave[0], j, g) for clave, (j, g) in por_jugador.items()]


def _total(bloque: Any) -> int | None:
    if not isinstance(bloque, dict) or bloque.get("total") is None:
        return None
    return int(_numero(bloque["total"]))


def _valor(g: Estadisticas, *nombres: str) -> Any:
    """First present stat among the spellings the API is documented/seen to use."""
    for nombre in nombres:
        if nombre in g:
            return g[nombre]
    return None


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
        completos, intentos = _par(_valor(g, "comp att", "completions/attempts"))
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
            "acarreos": _conteo(_valor(g, "carries", "total rushes")),
            "yardas": _entero(g.get("yards")),
            "touchdowns": _conteo(g.get("touchdowns")),
            "balonesSueltos": _conteo(g.get("fumbles lost")),
        }
    if (g := _grupo(grupos, _GRUPO_RECEPCION)) is not None:
        metricas["recepcion"] = {
            "objetivos": _conteo(g.get("targets")),
            "recepciones": _conteo(_valor(g, "receptions", "total receptions")),
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
        fg_anotados, fg_intentados = _par(_valor(g, "field goals", "fg made/att"))
        xp_anotados, xp_intentados = _par(_valor(g, "extra points", "xp made/att"))
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
