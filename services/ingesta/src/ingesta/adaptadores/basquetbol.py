"""NBA through api-basketball (league 12). First sport end to end (proposal §6.4: 1º NBA)."""

from datetime import date, datetime
from typing import Any

import pandas as pd

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

NBA_LEAGUE_ID = "12"

# api-basketball status.short → EstatusPartido
_ESTATUS = {
    "NS": EstatusPartido.PROGRAMADO,
    "FT": EstatusPartido.FINALIZADO,
    "AOT": EstatusPartido.FINALIZADO,
    "POST": EstatusPartido.POSPUESTO,
    "CANC": EstatusPartido.CANCELADO,
    "SUSP": EstatusPartido.POSPUESTO,
    "AWD": EstatusPartido.FINALIZADO,
    "ABD": EstatusPartido.CANCELADO,
}

# Box-score columns kept as integers in `metricas` (schemas/basquetbol.schema.json).
_COLUMNAS = {
    "points": "puntos",
    "rebounds.total": "rebotes",
    "assists": "asistencias",
    "field_goals.total": "tirosCampoAnotados",
    "field_goals.attempts": "tirosCampoIntentados",
    "threepoint_goals.total": "triplesAnotados",
    "threepoint_goals.attempts": "triplesIntentados",
    "freethrows_goals.total": "tirosLibresAnotados",
    "freethrows_goals.attempts": "tirosLibresIntentados",
}


class AdaptadorBasquetbol(AdaptadorDeporte):
    deporte = Deporte.BASQUETBOL
    proveedor = "api-sports"
    proveedor_liga_id = NBA_LEAGUE_ID

    def __init__(self, cliente: ClienteApiSports, temporada: str) -> None:
        self._cliente = cliente
        self._temporada = temporada

    def peticiones_usadas(self) -> int:
        return self._cliente.peticiones

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        return self._cliente.get(
            "/games",
            {"league": NBA_LEAGUE_ID, "season": self._temporada, "date": fecha.isoformat()},
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
                    temporada=str(p.get("league", {}).get("season", self._temporada)),
                    estatus=_ESTATUS.get(p["status"]["short"], EstatusPartido.EN_JUEGO),
                    local=EquipoNorm(str(local["id"]), local["name"], logo_url=local.get("logo")),
                    visita=EquipoNorm(
                        str(visita["id"]), visita["name"], logo_url=visita.get("logo")
                    ),
                    marcador_local=(scores.get("home") or {}).get("total"),
                    marcador_visita=(scores.get("away") or {}).get("total"),
                )
            )
        return resultado

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        if not lineas:
            return []
        df = pd.json_normalize(lineas)
        # Players who did not play come with null minutes and stats: drop them.
        df = df[df["minutes"].notna()].copy()
        if df.empty:
            return []
        df["minutos"] = df["minutes"].map(_minutos)
        for origen in _COLUMNAS:
            if origen not in df.columns:
                df[origen] = 0
        df[list(_COLUMNAS)] = df[list(_COLUMNAS)].fillna(0).astype(int).clip(lower=0)
        df = df.rename(columns=_COLUMNAS)

        return [
            EstadisticaNorm(
                partido_proveedor_id=partido_proveedor_id,
                equipo_proveedor_id=str(fila["team.id"]),
                jugador=JugadorNorm(str(fila["player.id"]), str(fila["player.name"])),
                minutos=fila["minutos"],
                metricas={col: int(fila[col]) for col in _COLUMNAS.values()},
            )
            for fila in df.to_dict(orient="records")
        ]


def _minutos(valor: object) -> int:
    """ "35:12" → 35; "35" → 35."""
    texto = str(valor)
    return int(texto.split(":", 1)[0]) if texto and texto[0].isdigit() else 0
