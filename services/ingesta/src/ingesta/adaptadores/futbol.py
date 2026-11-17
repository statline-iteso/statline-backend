"""Liga MX through api-football v3 (league 262). Mirrors AdaptadorBasquetbol (SL-17).

The field mapping follows the api-football documentation and was not checked against a live
response yet (no API key in development). See docs/DECISIONS.md, D-25.
"""

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

LIGA_MX_LEAGUE_ID = "262"

# api-football fixture.status.short → EstatusPartido
_ESTATUS = {
    "TBD": EstatusPartido.PROGRAMADO,
    "NS": EstatusPartido.PROGRAMADO,
    "1H": EstatusPartido.EN_JUEGO,
    "HT": EstatusPartido.EN_JUEGO,
    "2H": EstatusPartido.EN_JUEGO,
    "ET": EstatusPartido.EN_JUEGO,
    "BT": EstatusPartido.EN_JUEGO,
    "P": EstatusPartido.EN_JUEGO,
    "LIVE": EstatusPartido.EN_JUEGO,
    "INT": EstatusPartido.EN_JUEGO,
    "FT": EstatusPartido.FINALIZADO,
    "AET": EstatusPartido.FINALIZADO,
    "PEN": EstatusPartido.FINALIZADO,
    "AWD": EstatusPartido.FINALIZADO,
    "WO": EstatusPartido.FINALIZADO,
    "PST": EstatusPartido.POSPUESTO,
    "SUSP": EstatusPartido.POSPUESTO,
    "CANC": EstatusPartido.CANCELADO,
    "ABD": EstatusPartido.CANCELADO,
}

# Required by schemas/futbol.schema.json: a missing value is stored as 0 (as in the NBA adapter).
_REQUERIDAS = {
    "goles": ("goals", "total"),
    "asistencias": ("goals", "assists"),
}

# Optional metrics: a null from the provider is left out of `metricas` (the schema has no null).
_OPCIONALES_ENTERO = {
    "tiros": ("shots", "total"),
    "tirosAGol": ("shots", "on"),
    "pases": ("passes", "total"),
    "pasesClave": ("passes", "key"),
    "regates": ("dribbles", "success"),
    "entradas": ("tackles", "total"),
    "intercepciones": ("tackles", "interceptions"),
    "faltasCometidas": ("fouls", "committed"),
    "faltasRecibidas": ("fouls", "drawn"),
    "tarjetasAmarillas": ("cards", "yellow"),
    "tarjetasRojas": ("cards", "red"),
    "atajadas": ("goals", "saves"),
    "golesRecibidos": ("goals", "conceded"),
}


class AdaptadorFutbol(AdaptadorDeporte):
    deporte = Deporte.FUTBOL
    proveedor = "api-sports"
    proveedor_liga_id = LIGA_MX_LEAGUE_ID

    def __init__(self, cliente: ClienteApiSports, temporada: str) -> None:
        self._cliente = cliente
        self._temporada = temporada

    def peticiones_usadas(self) -> int:
        return self._cliente.peticiones

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        return self._cliente.get(
            "/fixtures",
            {"league": LIGA_MX_LEAGUE_ID, "season": self._temporada, "date": fecha.isoformat()},
        )

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        return self._cliente.get("/fixtures/players", {"fixture": partido_proveedor_id})

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        resultado: list[PartidoNorm] = []
        for p in partidos:
            fixture = p["fixture"]
            liga = p.get("league") or {}
            local, visita = p["teams"]["home"], p["teams"]["away"]
            goles = p.get("goals") or {}
            resultado.append(
                PartidoNorm(
                    proveedor_id=str(fixture["id"]),
                    fecha=datetime.fromisoformat(fixture["date"]),
                    temporada=str(liga.get("season", self._temporada)),
                    estatus=_ESTATUS.get(
                        (fixture.get("status") or {}).get("short", ""), EstatusPartido.EN_JUEGO
                    ),
                    local=EquipoNorm(str(local["id"]), local["name"], logo_url=local.get("logo")),
                    visita=EquipoNorm(
                        str(visita["id"]), visita["name"], logo_url=visita.get("logo")
                    ),
                    jornada=_jornada(liga.get("round")),
                    marcador_local=goles.get("home"),
                    marcador_visita=goles.get("away"),
                )
            )
        return resultado

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        # `lineas` is one block per team: {"team": {...}, "players": [{"player", "statistics"}]}.
        resultado: list[EstadisticaNorm] = []
        for bloque in lineas:
            equipo_id = str(bloque["team"]["id"])
            for entrada in bloque.get("players") or []:
                estadistica = _primera_estadistica(entrada)
                minutos = (estadistica.get("games") or {}).get("minutes")
                # Squad players who never came on come with null minutes and stats: drop them.
                if minutos is None:
                    continue
                jugador = entrada["player"]
                resultado.append(
                    EstadisticaNorm(
                        partido_proveedor_id=partido_proveedor_id,
                        equipo_proveedor_id=equipo_id,
                        jugador=JugadorNorm(
                            str(jugador["id"]),
                            str(jugador["name"]),
                            posicion=(estadistica.get("games") or {}).get("position"),
                        ),
                        minutos=_entero(minutos),
                        metricas=_metricas(estadistica),
                    )
                )
        return resultado


def _jornada(ronda: object) -> int | None:
    """ "Regular Season - 17" → 17. Playoff rounds without a number → None."""
    if not isinstance(ronda, str) or " - " not in ronda:
        return None
    sufijo = ronda.rsplit(" - ", 1)[1].strip()
    return int(sufijo) if sufijo.isdigit() else None


def _primera_estadistica(entrada: dict[str, Any]) -> dict[str, Any]:
    estadisticas = entrada.get("statistics") or []
    return dict(estadisticas[0]) if estadisticas else {}


def _metricas(estadistica: dict[str, Any]) -> dict[str, Any]:
    metricas: dict[str, Any] = {}
    for clave, (grupo, campo) in _REQUERIDAS.items():
        metricas[clave] = _entero(_campo(estadistica, grupo, campo)) or 0
    for clave, (grupo, campo) in _OPCIONALES_ENTERO.items():
        valor = _entero(_campo(estadistica, grupo, campo))
        if valor is not None:
            metricas[clave] = valor
    precision = _precision_pases(estadistica)
    if precision is not None:
        metricas["precisionPases"] = precision
    calificacion = _decimal(_campo(estadistica, "games", "rating"))
    if calificacion is not None:
        metricas["calificacion"] = min(calificacion, 10.0)
    return metricas


def _precision_pases(estadistica: dict[str, Any]) -> float | None:
    """Pass accuracy as a 0-100 percentage.

    In /fixtures/players `passes.accuracy` is the number of accurate passes (not a percentage),
    so it is divided by `passes.total`. A value carrying "%" is taken as already a percentage.
    """
    bruto = _campo(estadistica, "passes", "accuracy")
    valor = _decimal(bruto)
    if valor is None:
        return None
    if isinstance(bruto, str) and bruto.strip().endswith("%"):
        return min(valor, 100.0)
    total = _entero(_campo(estadistica, "passes", "total"))
    if not total:
        return None
    return round(min(valor / total * 100, 100.0), 1)


def _campo(estadistica: dict[str, Any], grupo: str, campo: str) -> object:
    return (estadistica.get(grupo) or {}).get(campo)


def _entero(valor: object) -> int | None:
    """Provider numbers are ints, sometimes strings, sometimes null. Negatives are clipped to 0."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return max(int(str(valor).strip()), 0)
    except ValueError:
        return None


def _decimal(valor: object) -> float | None:
    """ "78", "78.5" or "78%" → float. Negatives are clipped to 0."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return max(float(str(valor).strip().removesuffix("%")), 0.0)
    except ValueError:
        return None
