from datetime import UTC, date, datetime
from typing import Any

import httpx
import respx
from conftest import cargar

from ingesta.adaptadores.respaldo import ClienteRespaldo
from ingesta.adaptadores.thesportsdb import AdaptadorTheSportsDB
from ingesta.modelos import Deporte, EstatusPartido

BASE = "https://www.thesportsdb.com/api/v1/json/3"


def adaptador(deporte: Deporte = Deporte.AMERICANO) -> AdaptadorTheSportsDB:
    cliente = ClienteRespaldo(BASE, backoff_s=0)
    return AdaptadorTheSportsDB(cliente, deporte, "2026")


@respx.mock
def test_obtener_partidos_usa_eventsday_y_liga_de_la_nfl() -> None:
    ruta = respx.get(f"{BASE}/eventsday.php").mock(
        return_value=httpx.Response(200, json=cargar("thesportsdb_nfl_eventsday.json"))
    )
    a = adaptador(Deporte.AMERICANO)
    partidos = a.obtener_partidos(date(2026, 11, 15))
    assert len(partidos) == 3
    params = ruta.calls[0].request.url.params
    assert (params["d"], params["l"]) == ("2026-11-15", "4391")
    assert a.peticiones_usadas() == 1


@respx.mock
def test_liga_mx_usa_la_liga_4350() -> None:
    ruta = respx.get(f"{BASE}/eventsday.php").mock(
        return_value=httpx.Response(200, json=cargar("thesportsdb_ligamx_eventsday.json"))
    )
    adaptador(Deporte.FUTBOL).obtener_partidos(date(2026, 11, 14))
    assert ruta.calls[0].request.url.params["l"] == "4350"


@respx.mock
def test_dia_sin_partidos_con_events_null() -> None:
    respx.get(f"{BASE}/eventsday.php").mock(
        return_value=httpx.Response(200, json=cargar("thesportsdb_vacio.json"))
    )
    assert adaptador().obtener_partidos(date(2026, 12, 25)) == []


def test_normalizar_nfl_con_ids_namespaced_y_estatus() -> None:
    a = adaptador()
    final, programado, pospuesto = a.normalizar(cargar("thesportsdb_nfl_eventsday.json")["events"])

    assert final.proveedor_id == "thesportsdb:2201001"
    assert final.fecha == datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    assert final.temporada == "2026"
    assert final.estatus is EstatusPartido.FINALIZADO
    assert final.jornada == 10
    assert (final.local.proveedor_id, final.local.nombre) == (
        "thesportsdb:134168",
        "Dallas Cowboys",
    )
    assert final.local.logo_url is not None and final.visita.logo_url is None
    assert (final.marcador_local, final.marcador_visita) == (24, 27)

    assert programado.estatus is EstatusPartido.PROGRAMADO
    assert (programado.marcador_local, programado.marcador_visita) == (None, None)

    assert pospuesto.estatus is EstatusPartido.POSPUESTO
    assert pospuesto.fecha == datetime(2026, 11, 15, 0, 0, tzinfo=UTC)


def test_normalizar_liga_mx_con_marcador() -> None:
    a = adaptador(Deporte.FUTBOL)
    (partido,) = a.normalizar(cargar("thesportsdb_ligamx_eventsday.json")["events"])
    assert partido.proveedor_id == "thesportsdb:2202001"
    assert partido.estatus is EstatusPartido.FINALIZADO
    assert (partido.marcador_local, partido.marcador_visita) == (2, 1)
    assert partido.local.nombre == "Club America"


def test_sin_estadisticas_y_sin_peticiones_extra() -> None:
    a = adaptador()
    crudos: list[dict[str, Any]] = cargar("thesportsdb_nfl_eventsday.json")["events"]
    assert a.obtener_estadisticas("thesportsdb:2201001") == []
    assert a.normalizar_estadisticas("thesportsdb:2201001", crudos) == []
    assert a.peticiones_usadas() == 0
