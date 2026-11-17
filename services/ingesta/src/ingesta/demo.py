"""Synthetic demo data for local development. Dev only: no CronJob runs it.

`generar` is pure: same seed and reference date, same records. It returns the normalized
records the adapters produce (PartidoNorm, EstadisticaNorm), so `sembrar` writes them through the
same repository methods and validates every metrics line with `validar_metricas`.

Signal for the models: each team has a latent strength (mean skill of its best players) and each
player a latent skill. Game scores follow the strength difference plus home advantage. Box-score
lines follow the player skill, and team totals are split across the players who played, so they
add up to the final score.
"""

import logging
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from ingesta.modelos import (
    Deporte,
    EquipoNorm,
    EstadisticaNorm,
    EstatusPartido,
    JugadorNorm,
    PartidoNorm,
)
from ingesta.repositorio import Repositorio
from ingesta.validacion import validar_metricas

log = logging.getLogger(__name__)

PROVEEDOR = "demo"
PREFIJO = "demo-"
# The league rows come from `pnpm --filter @statline/api db:seed` (provider api-sports).
PROVEEDOR_LIGA = "api-sports"
LIGA_PROVEEDOR_ID = {Deporte.BASQUETBOL: "12", Deporte.AMERICANO: "1", Deporte.FUTBOL: "262"}
SEMILLA_DEFAULT = 42
DIAS_DEFAULT = 60
DIAS_PROGRAMADOS = 7

PORTERO = "Portero"
DEFENSA = "Defensa"
MEDIO = "Mediocampista"
DELANTERO = "Delantero"

_NOMBRES = (
    "Andrés", "Luis", "Carlos", "Miguel", "Diego", "Javier", "Rafael", "Sergio", "Mateo",
    "Ricardo", "Emilio", "Hugo", "Iván", "Óscar", "Tomás", "Gael", "Ramiro", "Samuel",
    "Daniel", "Adrián",
)  # fmt: skip
_APELLIDOS = (
    "Herrera", "Salinas", "Morales", "Castillo", "Ortega", "Vargas", "Navarro", "Ibarra",
    "Rojas", "Delgado", "Campos", "Medina", "Cárdenas", "Peña", "Robles", "Acosta", "Soto",
    "Vega", "Luna", "Fuentes", "Garza", "Mendoza", "Ríos", "Guzmán",
)  # fmt: skip
_MINUTOS_DE_INICIO = (0, 15, 30, 45)


@dataclass(frozen=True)
class PerfilDeporte:
    deporte: Deporte
    codigo: str
    equipos: tuple[tuple[str, str], ...]  # (nombre, abreviatura), fictitious names
    plantilla: tuple[str, ...]  # posición de cada jugador del equipo
    dias_juego: frozenset[int]  # date.weekday(): 0 = lunes
    partidos_por_dia: tuple[int, int]
    hora_utc: int


PERFILES: dict[Deporte, PerfilDeporte] = {
    Deporte.BASQUETBOL: PerfilDeporte(
        deporte=Deporte.BASQUETBOL,
        codigo="bas",
        equipos=(
            ("Halcones del Norte", "HNO"),
            ("Tiburones del Golfo", "TGO"),
            ("Lobos de la Sierra", "LSI"),
            ("Águilas del Valle", "AVA"),
            ("Osos del Pacífico", "OPA"),
            ("Cóndores del Altiplano", "CAL"),
            ("Pumas del Bajío", "PBA"),
            ("Tigres del Sur", "TSU"),
            ("Búhos de la Costa", "BCO"),
            ("Linces del Desierto", "LDE"),
        ),
        plantilla=("PG", "PG", "SG", "SG", "SG", "SF", "SF", "SF", "PF", "PF", "PF", "C", "C"),
        dias_juego=frozenset(range(7)),
        partidos_por_dia=(1, 4),
        hora_utc=0,
    ),
    Deporte.AMERICANO: PerfilDeporte(
        deporte=Deporte.AMERICANO,
        codigo="ame",
        equipos=(
            ("Truenos Metropolitanos", "TME"),
            ("Vaqueros del Río", "VRI"),
            ("Rayos del Oeste", "ROE"),
            ("Acorazados del Lago", "ALA"),
            ("Centinelas del Puerto", "CPU"),
            ("Mineros del Norte", "MNO"),
            ("Dragones de Acero", "DAC"),
            ("Faros del Mar", "FMA"),
            ("Galeones del Sur", "GSU"),
            ("Forjadores del Cañón", "FCA"),
        ),
        plantilla=(
            "QB",
            "QB",
            "RB",
            "RB",
            "WR",
            "WR",
            "TE",
            "DL",
            "DL",
            "LB",
            "LB",
            "CB",
            "CB",
            "S",
            "K",
        ),
        dias_juego=frozenset({3, 6}),
        partidos_por_dia=(1, 3),
        hora_utc=18,
    ),
    Deporte.FUTBOL: PerfilDeporte(
        deporte=Deporte.FUTBOL,
        codigo="fut",
        equipos=(
            ("Club Atlético Volcán", "VOL"),
            ("Deportivo Caminantes", "CAM"),
            ("Unión Coyotes", "UCO"),
            ("Club Ciervos Azules", "CAZ"),
            ("Sporting Mirador", "SMI"),
            ("Real Cosmos", "RCO"),
            ("Club Ánforas", "ANF"),
            ("Atlético Bahía", "ABA"),
            ("Deportivo Ébano", "DEB"),
            ("Club Fénix", "FEN"),
        ),
        plantilla=(
            PORTERO,
            PORTERO,
            DEFENSA,
            DEFENSA,
            DEFENSA,
            DEFENSA,
            DEFENSA,
            MEDIO,
            MEDIO,
            MEDIO,
            MEDIO,
            DELANTERO,
            DELANTERO,
            DELANTERO,
            DELANTERO,
        ),
        dias_juego=frozenset({2, 3, 5, 6}),
        partidos_por_dia=(2, 4),
        hora_utc=20,
    ),
}


@dataclass(frozen=True)
class PartidoDemo:
    partido: PartidoNorm
    lineas: tuple[EstadisticaNorm, ...] = ()


@dataclass(frozen=True)
class DatosDemo:
    deporte: Deporte
    partidos: tuple[PartidoDemo, ...]


@dataclass(frozen=True)
class _Jugador:
    jugador: JugadorNorm
    habilidad: float  # latente, ~N(0, 1)


@dataclass(frozen=True)
class _Equipo:
    norm: EquipoNorm
    fuerza: float  # latente: media de los mejores jugadores + ruido
    jugadores: tuple[_Jugador, ...]


def _posicion(jugador: _Jugador) -> str:
    return jugador.jugador.posicion or ""


# --- utilidades estadísticas (sin numpy) -------------------------------------------------------


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limite = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def _binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def _entero_acotado(rng: random.Random, mu: float, sigma: float, lo: int, hi: int) -> int:
    return min(hi, max(lo, round(rng.gauss(mu, sigma))))


def _reparto(total: int, pesos: list[float]) -> list[int]:
    """Split `total` proportionally to `pesos` with integer parts that add up exactly."""
    suma = sum(pesos)
    exactos = [total * p / suma for p in pesos]
    base = [math.floor(x) for x in exactos]
    orden = sorted(range(len(pesos)), key=lambda i: exactos[i] - base[i], reverse=True)
    for i in orden[: total - sum(base)]:
        base[i] += 1
    return base


# --- construcción de equipos y calendario ------------------------------------------------------


def _construir_equipos(perfil: PerfilDeporte, rng: random.Random) -> list[_Equipo]:
    equipos: list[_Equipo] = []
    for i, (nombre, abreviatura) in enumerate(perfil.equipos):
        jugadores = tuple(
            _Jugador(
                JugadorNorm(
                    f"{PREFIJO}{perfil.codigo}-p{i:02d}{j:02d}",
                    f"{rng.choice(_NOMBRES)} {rng.choice(_APELLIDOS)}",
                    posicion,
                ),
                rng.gauss(0.0, 1.0),
            )
            for j, posicion in enumerate(perfil.plantilla)
        )
        habilidades = sorted((j.habilidad for j in jugadores), reverse=True)
        mejores = max(3, len(habilidades) // 2)
        fuerza = sum(habilidades[:mejores]) / mejores + rng.gauss(0.0, 0.1)
        norm = EquipoNorm(f"{PREFIJO}{perfil.codigo}-t{i:02d}", nombre, abreviatura)
        equipos.append(_Equipo(norm, fuerza, jugadores))
    return equipos


def _emparejamientos(
    perfil: PerfilDeporte, rng: random.Random, dia: date, n: int
) -> list[tuple[int, int]]:
    if dia.weekday() not in perfil.dias_juego:
        return []
    orden = list(range(n))
    rng.shuffle(orden)
    cuantos = min(rng.randint(*perfil.partidos_por_dia), n // 2)
    return [(orden[2 * k], orden[2 * k + 1]) for k in range(cuantos)]


def generar(deporte: Deporte, *, semilla: int, dias: int, hoy: date, temporada: str) -> DatosDemo:
    """Finished games for the `dias` days before `hoy` and scheduled games for the next week."""
    if dias < 1:
        raise ValueError("dias debe ser al menos 1")
    perfil = PERFILES[deporte]
    rng = random.Random(f"{semilla}:{deporte.value}")
    equipos = _construir_equipos(perfil, rng)
    inicio = hoy - timedelta(days=dias)
    fechas = [inicio + timedelta(days=i) for i in range(dias)]
    fechas += [hoy + timedelta(days=i) for i in range(1, DIAS_PROGRAMADOS + 1)]

    partidos: list[PartidoDemo] = []
    for dia in fechas:
        jornada = None if deporte is Deporte.BASQUETBOL else (dia - inicio).days // 7 + 1
        for li, vi in _emparejamientos(perfil, rng, dia, len(equipos)):
            pid = f"{PREFIJO}{perfil.codigo}-g{len(partidos) + 1:05d}"
            fecha = datetime.combine(
                dia, time(perfil.hora_utc, rng.choice(_MINUTOS_DE_INICIO)), tzinfo=UTC
            )
            local, visita = equipos[li], equipos[vi]
            if dia < hoy:
                tl, tv, lineas = _simular(deporte, rng, pid, local, visita)
                partido = PartidoNorm(
                    pid, fecha, temporada, EstatusPartido.FINALIZADO,
                    local.norm, visita.norm, jornada, tl, tv,
                )  # fmt: skip
                partidos.append(PartidoDemo(partido, tuple(lineas)))
            else:
                partido = PartidoNorm(
                    pid, fecha, temporada, EstatusPartido.PROGRAMADO,
                    local.norm, visita.norm, jornada,
                )  # fmt: skip
                partidos.append(PartidoDemo(partido))
    return DatosDemo(deporte, tuple(partidos))


def _simular(
    deporte: Deporte, rng: random.Random, pid: str, local: _Equipo, visita: _Equipo
) -> tuple[int, int, list[EstadisticaNorm]]:
    if deporte is Deporte.BASQUETBOL:
        return _simular_basquetbol(rng, pid, local, visita)
    if deporte is Deporte.FUTBOL:
        return _simular_futbol(rng, pid, local, visita)
    return _simular_americano(rng, pid, local, visita)


# --- basquetbol (NBA) --------------------------------------------------------------------------


def _simular_basquetbol(
    rng: random.Random, pid: str, local: _Equipo, visita: _Equipo
) -> tuple[int, int, list[EstadisticaNorm]]:
    margen = 3.0 + 8.0 * (local.fuerza - visita.fuerza)  # ventaja de local incluida
    tl = _entero_acotado(rng, 112 + margen / 2, 10.0, 75, 150)
    tv = _entero_acotado(rng, 112 - margen / 2, 10.0, 75, 150)
    if tl == tv:  # no empates en la NBA
        tl += 1
    lineas = [
        *_lineas_basquetbol(rng, pid, local, tl, tl - tv),
        *_lineas_basquetbol(rng, pid, visita, tv, tv - tl),
    ]
    return tl, tv, lineas


def _rotacion_basquetbol(
    rng: random.Random, jugadores: tuple[_Jugador, ...]
) -> list[tuple[_Jugador, int]]:
    orden = sorted(jugadores, key=lambda j: j.habilidad, reverse=True)
    rotacion: list[tuple[_Jugador, int]] = []
    for i, jugador in enumerate(orden):
        if i < 5:
            minutos = rng.randint(26, 36)
        elif i < 10:
            minutos = rng.randint(12, 24)
        elif rng.random() < 0.5:
            minutos = rng.randint(3, 9)
        else:
            continue  # no jugó (DNP): el adaptador también los descarta
        rotacion.append((jugador, minutos))
    return rotacion


def _lineas_basquetbol(
    rng: random.Random, pid: str, equipo: _Equipo, puntos: int, diferencia: int
) -> list[EstadisticaNorm]:
    rotacion = _rotacion_basquetbol(rng, equipo.jugadores)
    pesos = [m * math.exp(0.5 * j.habilidad) * rng.uniform(0.8, 1.2) for j, m in rotacion]
    anotados = _reparto(puntos, pesos)
    lineas: list[EstadisticaNorm] = []
    for (jugador, minutos), pts in zip(rotacion, anotados, strict=True):
        metricas = _metricas_basquetbol(rng, jugador, minutos, pts, diferencia)
        lineas.append(
            EstadisticaNorm(pid, equipo.norm.proveedor_id, jugador.jugador, minutos, metricas)
        )
    return lineas


def _metricas_basquetbol(
    rng: random.Random, jugador: _Jugador, minutos: int, puntos: int, diferencia: int
) -> dict[str, Any]:
    esc = minutos / 36
    h = jugador.habilidad
    pos = _posicion(jugador)
    grande = pos in ("PF", "C")
    guardia = pos in ("PG", "SG")

    # Puntos = 2·dobles + 3·triples + libres, sin que sobren intentos. Ajustes de paridad abajo.
    t3a = max(0, round(rng.gauss(4.5 * esc + 0.6 * h, 1.0)))
    t3m = min(_binomial(rng, t3a, min(0.5, max(0.2, 0.35 + 0.03 * h))), puntos // 3)
    t3a = max(t3a, t3m)
    fta = max(0, round(rng.gauss(3.0 * esc + 0.4 * h, 1.0)))
    ftm = min(_binomial(rng, fta, 0.77), puntos - 3 * t3m)
    fta = max(fta, ftm)
    restante = puntos - 3 * t3m - ftm
    if restante % 2:  # hay que cerrar los puntos con dobles: un libre más lo arregla
        ftm += 1
        restante -= 1
        fta = max(fta, ftm)
    dos_m = restante // 2
    dos_a = max(dos_m, round(dos_m / 0.52 + rng.gauss(0.0, 1.0)))

    reb = _poisson(rng, (9.0 if grande else 4.5) * esc * math.exp(0.2 * h))
    reb_of = _binomial(rng, reb, 0.25)
    return {
        "puntos": puntos,
        "rebotes": reb,
        "rebotesOfensivos": reb_of,
        "rebotesDefensivos": reb - reb_of,
        "asistencias": _poisson(rng, (6.0 if guardia else 2.5) * esc * math.exp(0.25 * h)),
        "robos": _poisson(rng, 1.0 * esc),
        "bloqueos": _poisson(rng, (1.2 if grande else 0.4) * esc),
        "perdidas": _poisson(rng, 2.0 * esc),
        "faltas": min(6, _poisson(rng, 2.2 * esc)),
        "tirosCampoAnotados": dos_m + t3m,
        "tirosCampoIntentados": dos_a + t3a,
        "triplesAnotados": t3m,
        "triplesIntentados": t3a,
        "tirosLibresAnotados": ftm,
        "tirosLibresIntentados": fta,
        "masMenos": round(diferencia * minutos / 48 + rng.gauss(0.0, 4.0)),
    }


# --- futbol (Liga MX) --------------------------------------------------------------------------

_TITULARES_FUTBOL = ((PORTERO, 1), (DEFENSA, 4), (MEDIO, 3), (DELANTERO, 3))
_FACTOR_GOL = {PORTERO: 0.0, DEFENSA: 0.7, MEDIO: 2.0, DELANTERO: 4.0}
_FACTOR_ASISTENCIA = {PORTERO: 0.0, DEFENSA: 1.2, MEDIO: 2.5, DELANTERO: 1.0}
_FACTOR_TIRO = {PORTERO: 0.0, DEFENSA: 0.4, MEDIO: 0.9, DELANTERO: 1.5}
_FACTOR_PASE = {PORTERO: 0.8, DEFENSA: 1.0, MEDIO: 1.3, DELANTERO: 0.6}
_FACTOR_DEFENSA = {PORTERO: 0.0, DEFENSA: 1.6, MEDIO: 1.0, DELANTERO: 0.3}


def _simular_futbol(
    rng: random.Random, pid: str, local: _Equipo, visita: _Equipo
) -> tuple[int, int, list[EstadisticaNorm]]:
    dif = local.fuerza - visita.fuerza
    goles_l = _poisson(rng, 1.35 * math.exp(0.35 * dif + 0.15))
    goles_v = _poisson(rng, 1.15 * math.exp(-0.35 * dif))  # empates ocurren de forma natural
    lineas = [
        *_lineas_futbol(rng, pid, local, goles_l, goles_v),
        *_lineas_futbol(rng, pid, visita, goles_v, goles_l),
    ]
    return goles_l, goles_v, lineas


def _alineacion_futbol(
    rng: random.Random, jugadores: tuple[_Jugador, ...]
) -> list[tuple[_Jugador, int]]:
    rotacion: list[tuple[_Jugador, int]] = []
    for posicion, titulares in _TITULARES_FUTBOL:
        puesto = sorted(
            (j for j in jugadores if _posicion(j) == posicion),
            key=lambda j: j.habilidad,
            reverse=True,
        )
        for jugador in puesto[:titulares]:
            # El portero juega completo; el resto puede salir antes.
            sale = posicion != PORTERO and rng.random() < 0.3
            rotacion.append((jugador, rng.randint(55, 89) if sale else 90))
        for jugador in puesto[titulares:]:
            if rng.random() < 0.6:
                rotacion.append((jugador, rng.randint(8, 35)))
    return rotacion


def _lineas_futbol(
    rng: random.Random, pid: str, equipo: _Equipo, goles: int, recibidos: int
) -> list[EstadisticaNorm]:
    rotacion = _alineacion_futbol(rng, equipo.jugadores)
    anotados, asistidos = _asignar_goles(rng, rotacion, goles)
    lineas: list[EstadisticaNorm] = []
    for jugador, minutos in rotacion:
        clave = jugador.jugador.proveedor_id
        metricas = _metricas_futbol(
            rng, jugador, minutos / 90, anotados[clave], asistidos[clave], recibidos
        )
        lineas.append(
            EstadisticaNorm(pid, equipo.norm.proveedor_id, jugador.jugador, minutos, metricas)
        )
    return lineas


def _asignar_goles(
    rng: random.Random, rotacion: list[tuple[_Jugador, int]], goles: int
) -> tuple[dict[str, int], dict[str, int]]:
    """Each goal gets a scorer (and usually an assist) from the players on the field."""
    anotados = {j.jugador.proveedor_id: 0 for j, _ in rotacion}
    asistidos = dict.fromkeys(anotados, 0)
    campo = [(j, m) for j, m in rotacion if _posicion(j) != PORTERO]
    for _ in range(goles):
        pesos = [
            _FACTOR_GOL[_posicion(j)] * (m / 90) * math.exp(0.8 * j.habilidad) for j, m in campo
        ]
        goleador = rng.choices(campo, weights=pesos)[0][0]
        anotados[goleador.jugador.proveedor_id] += 1
        if rng.random() < 0.7:
            otros = [(j, m) for j, m in campo if j is not goleador]
            pesos_asistencia = [_FACTOR_ASISTENCIA[_posicion(j)] * (m / 90) for j, m in otros]
            asistente = rng.choices(otros, weights=pesos_asistencia)[0][0]
            asistidos[asistente.jugador.proveedor_id] += 1
    return anotados, asistidos


def _precision_pases(rng: random.Random, habilidad: float) -> float:
    return round(min(99.0, max(40.0, rng.gauss(78 + 3 * habilidad, 5))), 1)


def _metricas_futbol(
    rng: random.Random, jugador: _Jugador, esc: float, goles: int, asist: int, recibidos: int
) -> dict[str, Any]:
    h = jugador.habilidad
    pos = _posicion(jugador)
    calificacion = round(
        min(10.0, max(0.0, rng.gauss(6.5 + 0.3 * h + 0.4 * goles + 0.3 * asist, 0.6))), 1
    )
    metricas: dict[str, Any] = {
        "goles": goles,
        "asistencias": asist,
        "calificacion": calificacion,
        "faltasCometidas": _poisson(rng, 1.4 * esc),
        "faltasRecibidas": _poisson(rng, 1.4 * esc),
        "tarjetasAmarillas": min(2, _poisson(rng, 0.15 * esc)),
        "tarjetasRojas": 1 if rng.random() < 0.01 else 0,
    }
    if pos == PORTERO:
        metricas["atajadas"] = _poisson(rng, 3.0 * esc)
        metricas["golesRecibidos"] = recibidos
        metricas["pases"] = _poisson(rng, 20 * esc)
        metricas["precisionPases"] = _precision_pases(rng, h)
        return metricas

    tiros_sin_ajustar = _poisson(rng, 1.4 * esc * math.exp(0.3 * h) * _FACTOR_TIRO[pos])
    tiros_a_gol = max(goles, _binomial(rng, tiros_sin_ajustar, 0.35))
    metricas.update(
        {
            "tiros": max(tiros_sin_ajustar, tiros_a_gol),
            "tirosAGol": tiros_a_gol,
            "pases": _poisson(rng, 35 * esc * _FACTOR_PASE[pos]),
            "pasesClave": _poisson(rng, 1.2 * esc * _FACTOR_PASE[pos]),
            "precisionPases": _precision_pases(rng, h),
            "regates": _poisson(rng, 1.2 * esc * _FACTOR_TIRO[pos]),
            "entradas": _poisson(rng, 2.0 * esc * _FACTOR_DEFENSA[pos]),
            "intercepciones": _poisson(rng, 1.2 * esc * _FACTOR_DEFENSA[pos]),
        }
    )
    return metricas


# --- americano (NFL) ---------------------------------------------------------------------------

_PESO_RECEPTOR = {"WR": 3.0, "TE": 1.5, "RB": 1.0}
_TACLEADAS_POR_POSICION = {"DL": 3.0, "LB": 6.0, "CB": 4.0, "S": 5.0}


def _simular_americano(
    rng: random.Random, pid: str, local: _Equipo, visita: _Equipo
) -> tuple[int, int, list[EstadisticaNorm]]:
    dif = local.fuerza - visita.fuerza
    td_l = _poisson(rng, 2.4 * math.exp(0.25 * dif + 0.1))
    td_v = _poisson(rng, 2.4 * math.exp(-0.25 * dif))
    fg_l, fg_v = _poisson(rng, 1.6), _poisson(rng, 1.6)
    lineas = [
        *_lineas_americano(rng, pid, local, td_l, fg_l),
        *_lineas_americano(rng, pid, visita, td_v, fg_v),
    ]
    # Cada TD vale 7 (TD + punto extra convertido) y cada gol de campo 3.
    return 7 * td_l + 3 * fg_l, 7 * td_v + 3 * fg_v, lineas


def _por_posicion(jugadores: tuple[_Jugador, ...], posicion: str) -> list[_Jugador]:
    return sorted(
        (j for j in jugadores if _posicion(j) == posicion),
        key=lambda j: j.habilidad,
        reverse=True,
    )


def _lineas_americano(
    rng: random.Random, pid: str, equipo: _Equipo, anotaciones: int, goles_campo: int
) -> list[EstadisticaNorm]:
    """Team touchdowns split into passing (QB→receiver) and rushing, so the box score adds up."""
    qb = _por_posicion(equipo.jugadores, "QB")[0]
    receptores = [
        *_por_posicion(equipo.jugadores, "RB"),
        *_por_posicion(equipo.jugadores, "WR"),
        *_por_posicion(equipo.jugadores, "TE"),
    ]
    acarreadores = _por_posicion(equipo.jugadores, "RB")
    kicker = _por_posicion(equipo.jugadores, "K")[0]

    td_pase = sum(1 for _ in range(anotaciones) if rng.random() < 0.55)
    td_carrera = anotaciones - td_pase

    # Pases: intentos del QB, completos repartidos entre receptores, yardas = suma de recepciones.
    intentos = max(15, round(rng.gauss(33 + 2 * qb.habilidad, 4)))
    completos = min(intentos, max(td_pase, round(intentos * (0.6 + 0.03 * qb.habilidad))))
    pesos_recepcion = [
        _PESO_RECEPTOR[_posicion(j)] * math.exp(0.4 * j.habilidad) for j in receptores
    ]
    capturas = rng.choices(receptores, weights=pesos_recepcion, k=completos)
    recepciones: dict[str, int] = dict.fromkeys((j.jugador.proveedor_id for j in receptores), 0)
    yardas: dict[str, int] = dict(recepciones)
    tds_recepcion: dict[str, int] = dict(recepciones)
    for receptor in capturas:
        clave = receptor.jugador.proveedor_id
        recepciones[clave] += 1
        yardas[clave] += max(-3, round(rng.gauss(10.5, 6.0)))
    for indice in rng.sample(range(completos), td_pase):
        tds_recepcion[capturas[indice].jugador.proveedor_id] += 1

    # Acarreos: se reparten entre los RB; los TD de carrera caen en acarreos al azar.
    acarreos_total = max(12, round(rng.gauss(26, 4)))
    pesos_acarreo = [math.exp(0.3 * j.habilidad) for j in acarreadores]
    portadores = rng.choices(acarreadores, weights=pesos_acarreo, k=acarreos_total)
    acarreos: dict[str, int] = dict.fromkeys((j.jugador.proveedor_id for j in acarreadores), 0)
    yardas_carrera = dict(acarreos)
    td_acarreo = dict(acarreos)
    for portador in portadores:
        clave = portador.jugador.proveedor_id
        acarreos[clave] += 1
        yardas_carrera[clave] += max(-2, round(rng.gauss(4.2 + 0.2 * portador.habilidad, 3.0)))
    for indice in rng.sample(range(acarreos_total), td_carrera):
        td_acarreo[portadores[indice].jugador.proveedor_id] += 1

    metricas: dict[str, dict[str, Any]] = {}
    metricas[qb.jugador.proveedor_id] = {
        "pase": {
            "completos": completos,
            "intentos": intentos,
            "yardas": sum(yardas.values()),
            "touchdowns": td_pase,
            "intercepciones": _poisson(rng, 0.7),
        }
    }
    for receptor in receptores:
        clave = receptor.jugador.proveedor_id
        grupos = metricas.setdefault(clave, {})
        if recepciones[clave] or rng.random() < 0.3:
            grupos["recepcion"] = {
                "objetivos": recepciones[clave] + _poisson(rng, 0.8),
                "recepciones": recepciones[clave],
                "yardas": yardas[clave],
                "touchdowns": tds_recepcion[clave],
            }
    for portador in acarreadores:
        clave = portador.jugador.proveedor_id
        if acarreos[clave]:
            metricas.setdefault(clave, {})["carrera"] = {
                "acarreos": acarreos[clave],
                "yardas": yardas_carrera[clave],
                "touchdowns": td_acarreo[clave],
            }

    for posicion, lam in _TACLEADAS_POR_POSICION.items():
        for defensor in _por_posicion(equipo.jugadores, posicion):
            secundario = posicion in ("CB", "S")
            metricas.setdefault(defensor.jugador.proveedor_id, {})["defensa"] = {
                "tacleadas": _poisson(rng, lam),
                "capturas": round(abs(rng.gauss(0.8 if secundario else 1.0, 0.6)), 1),
                "intercepciones": _poisson(rng, 0.25 if secundario else 0.05),
                "pasesDefendidos": _poisson(rng, 0.6 if secundario else 0.0),
                "balonesForzados": _poisson(rng, 0.1),
            }
    metricas.setdefault(kicker.jugador.proveedor_id, {})["pateo"] = {
        "golesCampoAnotados": goles_campo,
        "golesCampoIntentados": goles_campo + _poisson(rng, 0.4),
        "puntosExtraAnotados": anotaciones,
        "puntosExtraIntentados": anotaciones + _poisson(rng, 0.2),
    }

    lineas: list[EstadisticaNorm] = []
    for jugador in equipo.jugadores:
        grupos_jugador = metricas.get(jugador.jugador.proveedor_id)
        if grupos_jugador:  # sin grupos no hay línea (el esquema exige al menos uno)
            lineas.append(
                EstadisticaNorm(
                    pid, equipo.norm.proveedor_id, jugador.jugador, 60, dict(grupos_jugador)
                )
            )
    return lineas


# --- escritura ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDemo:
    deporte: Deporte
    exitosa: bool
    partidos: int
    estadisticas: int
    error: str | None = None


def sembrar(
    repo: Repositorio,
    deporte: Deporte,
    *,
    temporada: str,
    semilla: int,
    dias: int,
    hoy: date,
    schemas_dir: str,
) -> ResultadoDemo:
    """Generate one sport's demo data and write it through the repository, like a normal run."""
    ejecucion_id = repo.iniciar_ejecucion(deporte, PROVEEDOR)
    partidos = estadisticas = 0
    error: str | None = None
    try:
        datos = generar(deporte, semilla=semilla, dias=dias, hoy=hoy, temporada=temporada)
        liga_id = repo.liga_id(deporte, PROVEEDOR_LIGA, LIGA_PROVEEDOR_ID[deporte])
        for pd in datos.partidos:
            partido_id = repo.guardar_partido(liga_id, pd.partido)
            partidos += 1
            if pd.partido.estatus is not EstatusPartido.FINALIZADO:
                continue
            for linea in pd.lineas:
                validar_metricas(schemas_dir, deporte, linea.metricas)
                repo.guardar_estadistica(deporte, liga_id, partido_id, linea)
                estadisticas += 1
    except Exception as err:
        error = f"{type(err).__name__}: {err}"
        log.exception("seed-demo fallido para %s", deporte)
    repo.finalizar_ejecucion(
        ejecucion_id,
        exitosa=error is None,
        registros=partidos + estadisticas,
        peticiones=0,
        error=error,
    )
    return ResultadoDemo(deporte, error is None, partidos, estadisticas, error)
