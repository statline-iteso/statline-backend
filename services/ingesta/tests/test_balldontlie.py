from datetime import UTC, date, datetime
from typing import Any

from conftest import cargar

from ingesta.adaptadores.balldontlie import AdaptadorBalldontlie, _estatus, _minutos
from ingesta.modelos import Deporte, EstatusPartido
from ingesta.validacion import validar_metricas


class ClienteFalso:
    def __init__(self) -> None:
        self.peticiones = 0
        self.llamadas: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.peticiones += 1
        self.llamadas.append((path, params))
        nombre = "balldontlie_games.json" if path == "/games" else "balldontlie_stats.json"
        cuerpo: dict[str, Any] = cargar(nombre)
        return cuerpo


def adaptador() -> tuple[AdaptadorBalldontlie, ClienteFalso]:
    cliente = ClienteFalso()
    return AdaptadorBalldontlie(cliente, "2025-2026"), cliente  # type: ignore[arg-type]


def test_obtener_partidos_pagina_y_usa_fecha() -> None:
    a, c = adaptador()
    partidos = a.obtener_partidos(date(2026, 11, 14))
    assert len(partidos) == 2
    assert c.llamadas == [("/games", {"dates[]": "2026-11-14", "per_page": 100})]


def test_obtener_estadisticas_quita_prefijo_del_id() -> None:
    a, c = adaptador()
    a.obtener_estadisticas("balldontlie:90001")
    assert c.llamadas == [("/stats", {"game_ids[]": "90001", "per_page": 100})]
    assert a.peticiones_usadas() == 1


def test_normalizar_partidos_con_ids_namespaced() -> None:
    a, _ = adaptador()
    final, programado = a.normalizar(cargar("balldontlie_games.json")["data"])

    assert final.proveedor_id == "balldontlie:90001"
    assert final.fecha == datetime(2026, 11, 14, 0, 30, tzinfo=UTC)
    assert final.temporada == "2025-2026"
    assert final.estatus is EstatusPartido.FINALIZADO
    assert final.local.proveedor_id == "balldontlie:8"
    assert final.local.nombre == "Denver Nuggets"
    assert final.local.abreviatura == "DEN"
    assert (final.marcador_local, final.marcador_visita) == (118, 111)

    assert programado.estatus is EstatusPartido.PROGRAMADO
    assert (programado.marcador_local, programado.marcador_visita) == (None, None)


def test_normalizar_estadisticas_valida_y_descarta_dnp(schemas_dir: str) -> None:
    a, _ = adaptador()
    lineas = a.normalizar_estadisticas(
        "balldontlie:90001", cargar("balldontlie_stats.json")["data"]
    )

    assert [linea.jugador.nombre for linea in lineas] == ["Nikola Jokić", "LeBron James"]
    jokic = lineas[0]
    assert jokic.minutos == 36
    assert jokic.equipo_proveedor_id == "balldontlie:8"
    assert jokic.jugador.proveedor_id == "balldontlie:3001"
    assert jokic.metricas["puntos"] == 31
    assert jokic.metricas["rebotesOfensivos"] == 3
    assert jokic.metricas["tirosCampoAnotados"] == 12
    assert jokic.metricas["triplesIntentados"] == 4
    assert jokic.metricas["tirosLibresIntentados"] == 7
    assert jokic.metricas["masMenos"] == 12

    james = lineas[1]
    # pts 25.0 (float) becomes an integer; a null optional stat is left out of metricas.
    assert james.metricas["puntos"] == 25
    assert "rebotesOfensivos" not in james.metricas
    assert james.metricas["masMenos"] == -6
    for linea in lineas:
        validar_metricas(schemas_dir, Deporte.BASQUETBOL, linea.metricas)


def test_normalizar_estadisticas_vacias() -> None:
    a, _ = adaptador()
    assert a.normalizar_estadisticas("balldontlie:1", []) == []


def test_estatus_de_balldontlie() -> None:
    assert _estatus("Final") is EstatusPartido.FINALIZADO
    assert _estatus("Final/OT") is EstatusPartido.FINALIZADO
    assert _estatus("Scheduled") is EstatusPartido.PROGRAMADO
    assert _estatus("7:30 pm ET") is EstatusPartido.PROGRAMADO
    assert _estatus("Postponed") is EstatusPartido.POSPUESTO
    assert _estatus("Canceled") is EstatusPartido.CANCELADO
    assert _estatus("3rd Qtr") is EstatusPartido.EN_JUEGO


def test_minutos_acepta_mm_ss_y_entero() -> None:
    assert _minutos("36:12") == 36
    assert _minutos("34") == 34
    assert _minutos("") is None
    assert _minutos(None) is None
