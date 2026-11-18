"""Deterministic synthetic games for the tests. Mirrors the shape of ingesta's demo seeder.

Team strength drives game scores (stronger teams win more). Rival strength drives player metrics
through what the rival allows, so the player models have signal to learn.
"""

import math
import random
from datetime import UTC, datetime, timedelta

import pandas as pd

from predicciones.deportes import OBJETIVOS_JUGADOR
from predicciones.schemas import Deporte

INICIO = datetime(2025, 9, 1, 20, tzinfo=UTC)


def _marcadores(deporte: Deporte, rng: random.Random, dif: float) -> tuple[int, int]:
    if deporte is Deporte.BASQUETBOL:
        ml = round(110 + 8 * dif + 3 + rng.gauss(0, 6))
        mv = round(110 - 8 * dif + rng.gauss(0, 6))
        return (ml, mv + 1) if ml == mv else (ml, mv)
    if deporte is Deporte.AMERICANO:
        ml = 7 * round(max(0.0, 2.3 + 0.8 * dif + rng.gauss(0, 1)))
        mv = 7 * round(max(0.0, 2.3 - 0.8 * dif + rng.gauss(0, 1)))
        return ml, mv
    ml = max(0, round(1.4 + 0.6 * dif + rng.gauss(0, 0.8)))
    mv = max(0, round(1.2 - 0.6 * dif + rng.gauss(0, 0.8)))
    return ml, mv


def generar_datos(
    deporte: Deporte,
    *,
    partidos: int = 300,
    equipos: int = 8,
    seed: int = 7,
    demo: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (partidos, lineas). Every game is finished; `demo` sets the `demo-` id prefix."""
    rng = random.Random(f"{seed}:{deporte.value}")
    prefijo = "demo-" if demo else "real-"
    fuerza = [rng.gauss(0, 1) for _ in range(equipos)]
    objetivos = OBJETIVOS_JUGADOR[deporte]
    roles = {
        Deporte.AMERICANO: ("pase", "carrera", "recepcion"),
    }.get(deporte)
    plantel: dict[int, list[tuple[str, float, str | None]]] = {}
    for t in range(equipos):
        plantel[t] = []
        for j in range(5):
            rol = roles[j % 3] if roles else None
            plantel[t].append((f"{prefijo}j{t:02d}{j}", rng.gauss(0, 1), rol))

    filas_partidos: list[dict[str, object]] = []
    filas_lineas: list[dict[str, object]] = []
    for i in range(partidos):
        local, visita = rng.sample(range(equipos), 2)
        fecha = INICIO + timedelta(days=i)
        ml, mv = _marcadores(deporte, rng, fuerza[local] - fuerza[visita])
        pid = f"{prefijo}p{i:05d}"
        filas_partidos.append(
            {
                "partido_id": pid,
                "fecha": fecha,
                "liga_id": "liga-1",
                "jornada": i // 4 + 1,
                "local_id": f"{prefijo}t{local}",
                "visita_id": f"{prefijo}t{visita}",
                "marcador_local": float(ml),
                "marcador_visita": float(mv),
                "proveedor_id": f"{prefijo}{i}",
                "es_demo": demo,
            }
        )
        for equipo, _rival, fuerza_rival in (
            (local, visita, fuerza[visita]),
            (visita, local, fuerza[local]),
        ):
            for jid, habilidad, rol in plantel[equipo]:
                minutos = rng.randint(20, 36) if deporte is Deporte.BASQUETBOL else 60
                fila: dict[str, object] = {
                    "partido_id": pid,
                    "jugador_id": jid,
                    "equipo_id": f"{prefijo}t{equipo}",
                    "fecha": fecha,
                    "local_id": f"{prefijo}t{local}",
                    "visita_id": f"{prefijo}t{visita}",
                    "minutos": minutos,
                    "es_demo": demo,
                }
                for obj in objetivos:
                    if roles and not obj.startswith(f"{rol}."):
                        fila[obj] = float("nan")
                        continue
                    # What a team allows is driven by the rival's strength (weaker defense ->
                    # more for the player); the player's own skill adds on top.
                    mu = 10 + 2.0 * habilidad - 3.0 * fuerza_rival
                    if deporte is Deporte.FUTBOL:
                        mu = max(0.2, 0.6 + 0.3 * habilidad - 0.4 * fuerza_rival)
                    elif deporte is Deporte.AMERICANO:
                        mu = max(0.0, 40 + 8 * habilidad - 6 * fuerza_rival)
                    else:
                        mu = max(0.0, mu)
                    fila[obj] = float(max(0, round(rng.gauss(mu, 1.5 + math.sqrt(mu) / 4))))
                filas_lineas.append(fila)
    return pd.DataFrame(filas_partidos), pd.DataFrame(filas_lineas)
