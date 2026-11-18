from datetime import date
from typing import Any

import pytest

from ingesta.demo import PERFILES, generar
from ingesta.modelos import Deporte, EstatusPartido
from ingesta.validacion import validar_metricas

HOY = date(2026, 11, 16)
TEMPORADAS = {Deporte.BASQUETBOL: "2025-2026", Deporte.AMERICANO: "2026", Deporte.FUTBOL: "2026"}


def datos(deporte: Deporte, semilla: int = 42) -> Any:
    return generar(deporte, semilla=semilla, dias=60, hoy=HOY, temporada=TEMPORADAS[deporte])


def finalizados(deporte: Deporte) -> list[Any]:
    return [p for p in datos(deporte).partidos if p.partido.estatus is EstatusPartido.FINALIZADO]


def test_misma_semilla_produce_los_mismos_datos() -> None:
    assert datos(Deporte.FUTBOL) == datos(Deporte.FUTBOL)


def test_otra_semilla_produce_otros_marcadores() -> None:
    marcadores = [p.partido.marcador_local for p in finalizados(Deporte.BASQUETBOL)]
    otros = [
        p.partido.marcador_local for p in datos(Deporte.BASQUETBOL, semilla=7).partidos
        if p.partido.estatus is EstatusPartido.FINALIZADO
    ]  # fmt: skip
    assert marcadores != otros


@pytest.mark.parametrize("deporte", list(Deporte))
def test_todas_las_lineas_validan_contra_el_esquema(schemas_dir: str, deporte: Deporte) -> None:
    lineas = [linea for p in datos(deporte).partidos for linea in p.lineas]
    assert lineas, "debe haber líneas de box score"
    for linea in lineas:
        validar_metricas(schemas_dir, deporte, linea.metricas)


@pytest.mark.parametrize("deporte", list(Deporte))
def test_plantilla_y_numero_de_equipos_son_razonables(deporte: Deporte) -> None:
    perfil = PERFILES[deporte]
    assert 8 <= len(perfil.equipos) <= 12
    assert 10 <= len(perfil.plantilla) <= 15


def test_futbol_tiene_empates() -> None:
    empates = [
        p
        for p in finalizados(Deporte.FUTBOL)
        if p.partido.marcador_local == p.partido.marcador_visita
    ]
    assert empates


def test_hay_partidos_programados_sin_lineas_en_la_proxima_semana() -> None:
    programados = [
        p
        for p in datos(Deporte.BASQUETBOL).partidos
        if p.partido.estatus is EstatusPartido.PROGRAMADO
    ]
    assert programados
    for p in programados:
        assert p.lineas == ()
        assert p.partido.marcador_local is None and p.partido.marcador_visita is None
        dia = p.partido.fecha.date()
        assert date(2026, 11, 17) <= dia <= date(2026, 11, 23)


def test_partidos_finalizados_son_anteriores_a_hoy() -> None:
    assert all(p.partido.fecha.date() < HOY for p in finalizados(Deporte.AMERICANO))


@pytest.mark.parametrize("deporte", list(Deporte))
def test_ids_llevan_prefijo_demo(deporte: Deporte) -> None:
    for p in datos(deporte).partidos:
        assert p.partido.proveedor_id.startswith("demo-")
        assert p.partido.local.proveedor_id.startswith("demo-")
        for linea in p.lineas:
            assert linea.jugador.proveedor_id.startswith("demo-")
            assert linea.equipo_proveedor_id.startswith("demo-")


def test_basquetbol_puntos_de_jugadores_suman_el_marcador() -> None:
    for p in finalizados(Deporte.BASQUETBOL):
        for equipo, marcador in (
            (p.partido.local.proveedor_id, p.partido.marcador_local),
            (p.partido.visita.proveedor_id, p.partido.marcador_visita),
        ):
            suma = sum(
                linea.metricas["puntos"]
                for linea in p.lineas
                if linea.equipo_proveedor_id == equipo
            )
            assert suma == marcador


def test_futbol_goles_de_jugadores_suman_el_marcador() -> None:
    for p in finalizados(Deporte.FUTBOL):
        for equipo, marcador in (
            (p.partido.local.proveedor_id, p.partido.marcador_local),
            (p.partido.visita.proveedor_id, p.partido.marcador_visita),
        ):
            suma = sum(
                linea.metricas["goles"] for linea in p.lineas if linea.equipo_proveedor_id == equipo
            )
            assert suma == marcador


def test_americano_marcador_cuadra_con_touchdowns_y_goles_de_campo() -> None:
    for p in finalizados(Deporte.AMERICANO):
        for equipo, marcador in (
            (p.partido.local.proveedor_id, p.partido.marcador_local),
            (p.partido.visita.proveedor_id, p.partido.marcador_visita),
        ):
            lineas = [linea for linea in p.lineas if linea.equipo_proveedor_id == equipo]
            td = sum(
                linea.metricas.get("pase", {}).get("touchdowns", 0)
                + linea.metricas.get("carrera", {}).get("touchdowns", 0)
                for linea in lineas
            )
            fg = sum(
                linea.metricas.get("pateo", {}).get("golesCampoAnotados", 0) for linea in lineas
            )
            assert 7 * td + 3 * fg == marcador


def test_generar_rechaza_dias_no_positivos() -> None:
    with pytest.raises(ValueError):
        generar(Deporte.FUTBOL, semilla=1, dias=0, hoy=HOY, temporada="2026")


def _porcentaje_victorias(partidos: list[Any]) -> dict[str, float]:
    puntos: dict[str, list[float]] = {}
    for p in partidos:
        n = p.partido
        local = 1.0 if n.marcador_local > n.marcador_visita else 0.0
        if n.marcador_local == n.marcador_visita:
            local = 0.5
        puntos.setdefault(n.local.proveedor_id, []).append(local)
        puntos.setdefault(n.visita.proveedor_id, []).append(1.0 - local)
    return {equipo: sum(v) / len(v) for equipo, v in puntos.items()}


@pytest.mark.parametrize("deporte", list(Deporte))
def test_la_fuerza_del_equipo_persiste_entre_mitades_de_temporada(deporte: Deporte) -> None:
    """The strength gap must be a real signal (D-36): first-half win % predicts the second half."""
    jugados = [
        p for p in generar(
            deporte, semilla=42, dias=240, hoy=HOY, temporada=TEMPORADAS[deporte]
        ).partidos
        if p.partido.estatus is EstatusPartido.FINALIZADO
    ]  # fmt: skip
    mitad = len(jugados) // 2
    primera = _porcentaje_victorias(jugados[:mitad])
    segunda = _porcentaje_victorias(jugados[mitad:])
    equipos = sorted(primera.keys() & segunda.keys())
    x = [primera[e] for e in equipos]
    y = [segunda[e] for e in equipos]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    var_x = sum((a - mx) ** 2 for a in x)
    var_y = sum((b - my) ** 2 for b in y)
    assert cov / (var_x * var_y) ** 0.5 > 0.5
