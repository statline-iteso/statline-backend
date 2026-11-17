import copy
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx
from conftest import cargar

from ingesta.adaptadores.api_sports import ClienteApiSports
from ingesta.adaptadores.futbol import AdaptadorFutbol, _jornada
from ingesta.modelos import Deporte, EstadisticaNorm, EstatusPartido, PartidoNorm
from ingesta.validacion import validar_metricas

BASE = "https://v3.football.api-sports.io"


class ClienteFalso:
    """Serves the recorded Liga MX fixtures by path, like ClienteApiSports.get."""

    def __init__(self, partidos: list[dict[str, Any]] | None = None) -> None:
        self.peticiones = 0
        self.llamadas: list[tuple[str, dict[str, Any]]] = []
        self._partidos = partidos

    def get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.peticiones += 1
        self.llamadas.append((path, params))
        if path == "/fixtures":
            if self._partidos is not None:
                return copy.deepcopy(self._partidos)
            respuesta: list[dict[str, Any]] = cargar("ligamx_fixtures.json")["response"]
            return respuesta
        respuesta_jugadores: list[dict[str, Any]] = cargar("ligamx_players.json")["response"]
        return respuesta_jugadores


def adaptador(cliente: ClienteFalso | None = None) -> tuple[AdaptadorFutbol, ClienteFalso]:
    cliente = cliente or ClienteFalso()
    return AdaptadorFutbol(cliente, "2026"), cliente  # type: ignore[arg-type]


def partidos_fixture() -> list[PartidoNorm]:
    a, _ = adaptador()
    return a.normalizar(cargar("ligamx_fixtures.json")["response"])


def lineas_fixture() -> list[EstadisticaNorm]:
    a, _ = adaptador()
    return a.normalizar_estadisticas("1208001", cargar("ligamx_players.json")["response"])


def por_nombre(lineas: list[EstadisticaNorm], nombre: str) -> EstadisticaNorm:
    return next(linea for linea in lineas if linea.jugador.nombre == nombre)


# --- I/O: parameters and paths -------------------------------------------------------------


def test_obtener_usa_liga_262_temporada_y_fecha() -> None:
    a, c = adaptador()
    a.obtener_partidos(date(2026, 11, 14))
    a.obtener_estadisticas("1208001")
    assert c.llamadas == [
        ("/fixtures", {"league": "262", "season": "2026", "date": "2026-11-14"}),
        ("/fixtures/players", {"fixture": "1208001"}),
    ]
    assert a.peticiones_usadas() == 2


def test_adaptador_declara_liga_mx() -> None:
    a, _ = adaptador()
    assert a.deporte is Deporte.FUTBOL
    assert a.proveedor_liga_id == "262"


@respx.mock
def test_flujo_http_con_cliente_real_y_respuesta_mock() -> None:
    fixtures = respx.get(f"{BASE}/fixtures").mock(
        return_value=httpx.Response(200, json=cargar("ligamx_fixtures.json"))
    )
    jugadores = respx.get(f"{BASE}/fixtures/players").mock(
        return_value=httpx.Response(200, json=cargar("ligamx_players.json"))
    )
    cliente = ClienteApiSports("football", "clave-de-prueba", backoff_s=0)
    a = AdaptadorFutbol(cliente, "2026")

    partidos = a.normalizar(a.obtener_partidos(date(2026, 11, 14)))
    lineas = a.normalizar_estadisticas("1208001", a.obtener_estadisticas("1208001"))

    assert len(partidos) == 3
    assert len(lineas) == 4
    params = dict(fixtures.calls[0].request.url.params)
    assert params == {"league": "262", "season": "2026", "date": "2026-11-14"}
    assert dict(jugadores.calls[0].request.url.params) == {"fixture": "1208001"}
    assert fixtures.calls[0].request.headers["x-apisports-key"] == "clave-de-prueba"
    assert cliente.peticiones == 2


# --- normalizar: partidos ------------------------------------------------------------------


def test_normalizar_partido_finalizado() -> None:
    final, _, _ = partidos_fixture()

    assert final.proveedor_id == "1208001"
    assert final.fecha == datetime(2026, 11, 14, 2, 0, tzinfo=UTC)
    assert final.temporada == "2026"
    assert final.estatus is EstatusPartido.FINALIZADO
    assert (final.local.proveedor_id, final.local.nombre) == ("1000", "Club Local")
    assert (final.visita.proveedor_id, final.visita.nombre) == ("1001", "Club Visitante")
    assert final.local.logo_url == "https://media.api-sports.io/football/teams/1000.png"
    assert (final.marcador_local, final.marcador_visita) == (2, 1)
    assert final.jornada == 17


def test_normalizar_partido_programado_sin_marcador() -> None:
    _, programado, _ = partidos_fixture()
    assert programado.estatus is EstatusPartido.PROGRAMADO
    assert programado.visita.logo_url is None
    assert (programado.marcador_local, programado.marcador_visita) == (None, None)
    assert programado.jornada == 18


def test_normalizar_partido_pospuesto() -> None:
    *_, pospuesto = partidos_fixture()
    assert pospuesto.estatus is EstatusPartido.POSPUESTO


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("TBD", EstatusPartido.PROGRAMADO),
        ("NS", EstatusPartido.PROGRAMADO),
        ("1H", EstatusPartido.EN_JUEGO),
        ("HT", EstatusPartido.EN_JUEGO),
        ("2H", EstatusPartido.EN_JUEGO),
        ("ET", EstatusPartido.EN_JUEGO),
        ("BT", EstatusPartido.EN_JUEGO),
        ("P", EstatusPartido.EN_JUEGO),
        ("INT", EstatusPartido.EN_JUEGO),
        ("FT", EstatusPartido.FINALIZADO),
        ("AET", EstatusPartido.FINALIZADO),
        ("PEN", EstatusPartido.FINALIZADO),
        ("AWD", EstatusPartido.FINALIZADO),
        ("WO", EstatusPartido.FINALIZADO),
        ("PST", EstatusPartido.POSPUESTO),
        ("SUSP", EstatusPartido.POSPUESTO),
        ("CANC", EstatusPartido.CANCELADO),
        ("ABD", EstatusPartido.CANCELADO),
        ("Q9", EstatusPartido.EN_JUEGO),
    ],
)
def test_mapeo_de_estatus(codigo: str, esperado: EstatusPartido) -> None:
    a, _ = adaptador()
    crudo = copy.deepcopy(cargar("ligamx_fixtures.json")["response"][0])
    crudo["fixture"]["status"]["short"] = codigo
    assert a.normalizar([crudo])[0].estatus is esperado


@pytest.mark.parametrize(
    ("ronda", "jornada"),
    [
        ("Regular Season - 17", 17),
        ("Regular Season - 1", 1),
        ("Apertura - 3", 3),
        ("Liguilla - Quarter-finals", None),
        ("Final", None),
        ("", None),
        (None, None),
    ],
)
def test_jornada_desde_la_ronda(ronda: str | None, jornada: int | None) -> None:
    assert _jornada(ronda) == jornada


def test_partido_sin_bloque_league_usa_temporada_del_adaptador() -> None:
    a, _ = adaptador()
    crudo = copy.deepcopy(cargar("ligamx_fixtures.json")["response"][0])
    crudo.pop("league")
    crudo["goals"] = None
    partido = a.normalizar([crudo])[0]
    assert partido.temporada == "2026"
    assert partido.jornada is None
    assert (partido.marcador_local, partido.marcador_visita) == (None, None)


# --- normalizar_estadisticas ---------------------------------------------------------------


def test_normalizar_estadisticas_descarta_suplentes_sin_minutos() -> None:
    lineas = lineas_fixture()
    nombres = [linea.jugador.nombre for linea in lineas]
    assert nombres == ["J. Ejemplo", "M. Prueba", "R. Demo", "D. Visita"]
    assert "S. Banca" not in nombres


def test_normalizar_estadisticas_identidad_y_equipo() -> None:
    lineas = lineas_fixture()
    ejemplo = por_nombre(lineas, "J. Ejemplo")
    assert ejemplo.partido_proveedor_id == "1208001"
    assert ejemplo.equipo_proveedor_id == "1000"
    assert ejemplo.jugador.proveedor_id == "5001"
    assert ejemplo.jugador.posicion == "Attacker"
    assert ejemplo.minutos == 90
    assert por_nombre(lineas, "D. Visita").equipo_proveedor_id == "1001"


def test_normalizar_estadisticas_mapea_metricas() -> None:
    ejemplo = por_nombre(lineas_fixture(), "J. Ejemplo")
    assert ejemplo.metricas == {
        "goles": 1,
        "asistencias": 1,
        "tiros": 4,
        "tirosAGol": 2,
        "pases": 32,
        "pasesClave": 2,
        "precisionPases": 78.0,
        "regates": 3,
        "entradas": 1,
        "intercepciones": 1,
        "faltasCometidas": 1,
        "faltasRecibidas": 3,
        "tarjetasAmarillas": 0,
        "tarjetasRojas": 0,
        "golesRecibidos": 0,
        "calificacion": 8.1,
    }


def test_portero_usa_atajadas_y_nulos_se_omiten() -> None:
    portero = por_nombre(lineas_fixture(), "R. Demo")
    assert portero.jugador.posicion == "Goalkeeper"
    assert portero.metricas["atajadas"] == 4
    assert portero.metricas["golesRecibidos"] == 1
    assert portero.metricas["goles"] == 0
    # Provider nulls for optional metrics are left out, never stored as null.
    assert "tiros" not in portero.metricas
    assert "pasesClave" not in portero.metricas
    assert "precisionPases" not in portero.metricas
    assert "calificacion" in portero.metricas


def test_nulos_en_requeridas_se_guardan_como_cero() -> None:
    medio = por_nombre(lineas_fixture(), "M. Prueba")
    assert medio.metricas["goles"] == 0
    assert medio.metricas["asistencias"] == 0
    assert medio.metricas["tarjetasAmarillas"] == 2
    assert medio.metricas["precisionPases"] == 91.0
    assert medio.minutos == 78


def test_todas_las_lineas_validan_contra_el_esquema(schemas_dir: str) -> None:
    lineas = lineas_fixture()
    assert lineas
    for linea in lineas:
        validar_metricas(schemas_dir, Deporte.FUTBOL, linea.metricas)


def test_estadisticas_vacias_y_bloques_sin_jugadores() -> None:
    a, _ = adaptador()
    assert a.normalizar_estadisticas("1", []) == []
    assert a.normalizar_estadisticas("1", [{"team": {"id": 1}, "players": None}]) == []


def test_jugador_sin_estadisticas_es_dnp() -> None:
    a, _ = adaptador()
    bloque = {
        "team": {"id": 9},
        "players": [{"player": {"id": 1, "name": "X"}, "statistics": []}],
    }
    assert a.normalizar_estadisticas("1", [bloque]) == []


def test_porcentajes_y_calificaciones_se_limitan_y_se_parsean() -> None:
    a, _ = adaptador()
    bloque = copy.deepcopy(cargar("ligamx_players.json")["response"][0])
    estadistica = bloque["players"][0]["statistics"][0]
    estadistica["passes"]["accuracy"] = "78%"
    estadistica["games"]["rating"] = "11.5"
    estadistica["shots"]["total"] = "-2"
    estadistica["shots"]["on"] = "abc"
    lineas = a.normalizar_estadisticas("1208001", [bloque])
    ejemplo = por_nombre(lineas, "J. Ejemplo")
    assert ejemplo.metricas["precisionPases"] == 78.0
    assert ejemplo.metricas["calificacion"] == 10.0
    assert ejemplo.metricas["tiros"] == 0
    assert "tirosAGol" not in ejemplo.metricas


def test_precision_mayor_a_cien_se_limita() -> None:
    a, _ = adaptador()
    bloque = copy.deepcopy(cargar("ligamx_players.json")["response"][0])
    bloque["players"][0]["statistics"][0]["passes"]["accuracy"] = 120
    ejemplo = por_nombre(a.normalizar_estadisticas("1", [bloque]), "J. Ejemplo")
    assert ejemplo.metricas["precisionPases"] == 100.0


def test_valores_booleanos_se_tratan_como_nulos() -> None:
    a, _ = adaptador()
    bloque = copy.deepcopy(cargar("ligamx_players.json")["response"][0])
    bloque["players"][0]["statistics"][0]["shots"]["total"] = True
    bloque["players"][0]["statistics"][0]["passes"]["accuracy"] = False
    ejemplo = por_nombre(a.normalizar_estadisticas("1", [bloque]), "J. Ejemplo")
    assert "tiros" not in ejemplo.metricas
    assert "precisionPases" not in ejemplo.metricas


def test_minutos_cero_se_conservan() -> None:
    a, _ = adaptador()
    bloque = copy.deepcopy(cargar("ligamx_players.json")["response"][0])
    bloque["players"][0]["statistics"][0]["games"]["minutes"] = 0
    ejemplo = por_nombre(a.normalizar_estadisticas("1", [bloque]), "J. Ejemplo")
    assert ejemplo.minutos == 0


def test_normalizar_lista_vacia() -> None:
    a, _ = adaptador()
    assert a.normalizar([]) == []


def test_fecha_conserva_la_zona_horaria_del_proveedor() -> None:
    final, *_ = partidos_fixture()
    assert final.fecha.tzinfo is not None
    assert final.fecha.astimezone(UTC).hour == 2
