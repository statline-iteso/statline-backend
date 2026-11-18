"""Feature extraction (SL-33). Pure functions: no I/O, no SQL, no clock.

No leakage by construction: every feature of a row is computed from rows whose date is strictly
before the row's date (`_Serie.previos`). A game's own result never enters its own features.
"""

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from predicciones.deportes import VENTANA_DEFAULT

DIAS_DESCANSO_MAX = 14.0
RASGOS_EQUIPO: tuple[str, ...] = (
    "puntos_favor",
    "puntos_contra",
    "tasa_victorias",
    "tasa_victorias_local",
    "tasa_victorias_visita",
    "dias_descanso",
)
_NAN = float("nan")


@dataclass
class _Serie[T]:
    """Chronological history of one entity (team or player)."""

    fechas: list[pd.Timestamp] = field(default_factory=list)
    valores: list[T] = field(default_factory=list)

    def agregar(self, fecha: pd.Timestamp, valor: T) -> None:
        self.fechas.append(fecha)
        self.valores.append(valor)

    def ordenar(self) -> None:
        orden = sorted(range(len(self.fechas)), key=lambda i: self.fechas[i])
        self.fechas = [self.fechas[i] for i in orden]
        self.valores = [self.valores[i] for i in orden]

    def corte(self, fecha: pd.Timestamp) -> int:
        """Number of entries strictly before `fecha`."""
        return bisect_left(self.fechas, fecha)

    def previos(self, fecha: pd.Timestamp, ventana: int) -> list[T]:
        """The last `ventana` entries strictly before `fecha`, oldest first."""
        hasta = self.corte(fecha)
        return self.valores[max(0, hasta - ventana) : hasta]


def _media(valores: Sequence[float]) -> float:
    """Mean ignoring NaN; NaN when nothing is left."""
    limpios = [v for v in valores if not np.isnan(v)]
    return float(sum(limpios) / len(limpios)) if limpios else _NAN


def _validar_ventana(ventana: int) -> None:
    if ventana < 1:
        raise ValueError("ventana debe ser al menos 1")


# --- equipos ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _RegistroEquipo:
    puntos_favor: float
    puntos_contra: float
    victoria: float
    es_local: bool


def _historial_equipos(partidos: pd.DataFrame) -> dict[str, _Serie[_RegistroEquipo]]:
    """Per team, each finished game (from both sides) as a `_RegistroEquipo`, oldest first."""
    historial: dict[str, _Serie[_RegistroEquipo]] = {}
    terminados = partidos.dropna(subset=["marcador_local", "marcador_visita"])
    for pid_fecha, local, visita, ml, mv in zip(
        zip(terminados["partido_id"], terminados["fecha"], strict=True),
        terminados["local_id"],
        terminados["visita_id"],
        terminados["marcador_local"].astype(float),
        terminados["marcador_visita"].astype(float),
        strict=True,
    ):
        fecha = pid_fecha[1]
        historial.setdefault(local, _Serie()).agregar(
            fecha, _RegistroEquipo(ml, mv, float(ml > mv), True)
        )
        historial.setdefault(visita, _Serie()).agregar(
            fecha, _RegistroEquipo(mv, ml, float(mv > ml), False)
        )
    for serie in historial.values():
        serie.ordenar()
    return historial


def _rasgos_equipo(
    serie: _Serie[_RegistroEquipo] | None, fecha: pd.Timestamp, ventana: int
) -> dict[str, float]:
    if serie is None:
        return dict.fromkeys(RASGOS_EQUIPO, _NAN)
    hasta = serie.corte(fecha)
    previos = serie.valores[:hasta]
    ultimos = previos[-ventana:]
    locales = [r for r in previos if r.es_local][-ventana:]
    visitas = [r for r in previos if not r.es_local][-ventana:]
    if hasta:
        dias = (fecha - serie.fechas[hasta - 1]).total_seconds() / 86400
        descanso = min(dias, DIAS_DESCANSO_MAX)
    else:
        descanso = _NAN
    return {
        "puntos_favor": _media([r.puntos_favor for r in ultimos]),
        "puntos_contra": _media([r.puntos_contra for r in ultimos]),
        "tasa_victorias": _media([r.victoria for r in ultimos]),
        "tasa_victorias_local": _media([r.victoria for r in locales]),
        "tasa_victorias_visita": _media([r.victoria for r in visitas]),
        "dias_descanso": descanso,
    }


def nombres_features_partido() -> tuple[str, ...]:
    return tuple(
        [f"{lado}_{rasgo}" for lado in ("local", "visita") for rasgo in RASGOS_EQUIPO]
        + [f"dif_{rasgo}" for rasgo in RASGOS_EQUIPO]
    )


def features_partidos(partidos: pd.DataFrame, ventana: int = VENTANA_DEFAULT) -> pd.DataFrame:
    """Team features for every game in `partidos`, indexed by partido_id.

    `partidos` needs: partido_id, fecha, local_id, visita_id, marcador_local, marcador_visita
    (NaN for games not played yet). Rows with a score form the history; every row gets features.

    Columns (see nombres_features_partido): `local_<rasgo>`, `visita_<rasgo>` and `dif_<rasgo>`
    (local minus visita). Each team uses its last `ventana` games strictly before the date.
    """
    _validar_ventana(ventana)
    fechas = pd.to_datetime(partidos["fecha"], utc=True)
    historial = _historial_equipos(partidos.assign(fecha=fechas))
    filas: list[dict[str, float]] = []
    for fecha, local_id, visita_id in zip(
        fechas, partidos["local_id"], partidos["visita_id"], strict=True
    ):
        local = _rasgos_equipo(historial.get(local_id), fecha, ventana)
        visita = _rasgos_equipo(historial.get(visita_id), fecha, ventana)
        registro: dict[str, float] = {}
        for rasgo in RASGOS_EQUIPO:
            registro[f"local_{rasgo}"] = local[rasgo]
            registro[f"visita_{rasgo}"] = visita[rasgo]
            registro[f"dif_{rasgo}"] = local[rasgo] - visita[rasgo]
        filas.append(registro)
    return pd.DataFrame(
        filas,
        index=pd.Index(partidos["partido_id"].to_numpy(), name="partido_id"),
        columns=pd.Index(nombres_features_partido()),
        dtype=float,
    )


# --- jugadores -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _RegistroJugador:
    minutos: float
    valores: dict[str, float]


def _historial_jugadores(
    historial: pd.DataFrame, objetivos: Sequence[str]
) -> dict[str, _Serie[_RegistroJugador]]:
    jugadores: dict[str, _Serie[_RegistroJugador]] = {}
    for fila in historial.assign(minutos=historial["minutos"].astype(float)).to_dict("records"):
        valores = {obj: float(fila[obj]) for obj in objetivos}
        serie = jugadores.setdefault(str(fila["jugador_id"]), _Serie())
        serie.agregar(fila["fecha"], _RegistroJugador(fila["minutos"], valores))
    for serie in jugadores.values():
        serie.ordenar()
    return jugadores


def _permitido_por_equipo(
    historial: pd.DataFrame, objetivos: Sequence[str]
) -> dict[str, _Serie[dict[str, float]]]:
    """Per team, what it allowed in each game: the rival's total of every target metric."""
    totales = (
        historial.groupby(["partido_id", "equipo_id"])[list(objetivos)]
        .sum(min_count=1)
        .to_dict(orient="index")
    )
    permitido: dict[str, _Serie[dict[str, float]]] = {}
    partidos = historial.drop_duplicates("partido_id")
    for pid, fecha, local, visita in zip(
        partidos["partido_id"],
        partidos["fecha"],
        partidos["local_id"],
        partidos["visita_id"],
        strict=True,
    ):
        for equipo, rival in ((local, visita), (visita, local)):
            fila = totales.get((pid, rival), {})
            valores = {obj: float(fila.get(obj, _NAN)) for obj in objetivos}
            permitido.setdefault(str(equipo), _Serie()).agregar(fecha, valores)
    for serie in permitido.values():
        serie.ordenar()
    return permitido


def nombres_features_jugador(objetivos: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        [f"prom_{o}" for o in objetivos]
        + ["minutos_prom", "es_local"]
        + [f"rival_{o}_permitido" for o in objetivos]
    )


def features_jugadores(
    historial: pd.DataFrame,
    consultas: pd.DataFrame,
    objetivos: Sequence[str],
    ventana: int = VENTANA_DEFAULT,
) -> pd.DataFrame:
    """Player features for each row of `consultas`, aligned to its index.

    `historial` holds finished player lines: partido_id, jugador_id, equipo_id, local_id,
    visita_id, fecha, minutos and one column per objetivo (dotted names allowed). `consultas`
    holds the rows to featurize: training passes the same lines; inference passes the expected
    lineup of a scheduled game (only jugador_id, equipo_id, local_id, visita_id, fecha needed).
    Only history strictly before each row's date is used.

    Columns (see nombres_features_jugador): `prom_<obj>` (mean of the player's last `ventana`
    games), `minutos_prom`, `es_local`, and `rival_<obj>_permitido` (mean over the rival's last
    `ventana` games of what it allowed, i.e. its rivals' team totals).
    """
    _validar_ventana(ventana)
    objetivos = tuple(objetivos)
    hist = historial.assign(fecha=pd.to_datetime(historial["fecha"], utc=True))
    fechas_cons = pd.to_datetime(consultas["fecha"], utc=True)
    jugadores = _historial_jugadores(hist, objetivos)
    permitido = _permitido_por_equipo(hist, objetivos)

    filas: list[dict[str, float]] = []
    for jugador_id, equipo_id, local_id, visita_id, fecha in zip(
        consultas["jugador_id"],
        consultas["equipo_id"],
        consultas["local_id"],
        consultas["visita_id"],
        fechas_cons,
        strict=True,
    ):
        serie = jugadores.get(str(jugador_id))
        previos = serie.previos(fecha, ventana) if serie else []
        registro: dict[str, float] = {}
        for obj in objetivos:
            registro[f"prom_{obj}"] = _media([r.valores[obj] for r in previos])
        registro["minutos_prom"] = _media([r.minutos for r in previos])
        es_local = str(equipo_id) == str(local_id)
        registro["es_local"] = float(es_local)
        rival = str(visita_id) if es_local else str(local_id)
        serie_rival = permitido.get(rival)
        previos_rival = serie_rival.previos(fecha, ventana) if serie_rival else []
        for obj in objetivos:
            registro[f"rival_{obj}_permitido"] = _media([p[obj] for p in previos_rival])
        filas.append(registro)
    return pd.DataFrame(
        filas,
        index=consultas.index,
        columns=pd.Index(nombres_features_jugador(objetivos)),
        dtype=float,
    )
