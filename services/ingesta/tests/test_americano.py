from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx
from conftest import cargar

from ingesta.adaptadores import crear_adaptador
from ingesta.adaptadores.americano import AdaptadorAmericano, _par
from ingesta.adaptadores.api_sports import ClienteApiSports
from ingesta.config import Settings
from ingesta.modelos import Deporte, EstatusPartido
from ingesta.validacion import validar_metricas

BASE = "https://v1.american-football.api-sports.io"


def adaptador() -> AdaptadorAmericano:
    cliente = ClienteApiSports("american-football", "clave-de-prueba", backoff_s=0)
    return AdaptadorAmericano(cliente, "2026")


def linea(grupos: list[dict[str, Any]], nombre: str = "Jugador Prueba") -> dict[str, Any]:
    return {
        "team": {"id": 10},
        "player": {"id": 9001, "name": nombre, "position": "QB"},
        "groups": grupos,
    }  # legacy one-entry-per-player shape; real shape is built by `equipo`


def equipo(
    jugadores: dict[tuple[int, str], list[dict[str, Any]]], team_id: int = 10
) -> dict[str, Any]:
    """Real shape: one entry per team, players nested inside each category group."""
    nombres = {g["name"] for gs in jugadores.values() for g in gs}
    return {
        "team": {"id": team_id},
        "groups": [
            {
                "name": n,
                "players": [
                    {"player": {"id": pid, "name": nom}, "statistics": g["statistics"]}
                    for (pid, nom), gs in jugadores.items()
                    for g in gs
                    if g["name"] == n
                ],
            }
            for n in sorted(nombres)
        ],
    }


def grupo(nombre: str, **valores: Any) -> dict[str, Any]:
    stats = [{"name": k.replace("_", " "), "value": v} for k, v in valores.items()]
    return {"name": nombre, "statistics": stats}


@respx.mock
def test_obtener_partidos_usa_liga_nfl_temporada_y_fecha() -> None:
    ruta = respx.get(f"{BASE}/games").mock(
        return_value=httpx.Response(
            200, json={"errors": [], "response": cargar("nfl_games.json")["response"]}
        )
    )
    a = adaptador()
    assert len(a.obtener_partidos(date(2026, 11, 15))) == 3
    assert dict(ruta.calls[0].request.url.params) == {
        "league": "1",
        "season": "2026",
        "date": "2026-11-15",
    }
    assert ruta.calls[0].request.headers["x-apisports-key"] == "clave-de-prueba"
    assert a.peticiones_usadas() == 1


@respx.mock
def test_obtener_estadisticas_llama_al_endpoint_de_jugadores() -> None:
    ruta = respx.get(f"{BASE}/games/statistics/players").mock(
        return_value=httpx.Response(
            200, json={"errors": [], "response": cargar("nfl_players_stats.json")["response"]}
        )
    )
    a = adaptador()
    assert len(a.obtener_estadisticas("1001")) == 2
    assert dict(ruta.calls[0].request.url.params) == {"id": "1001"}


def test_normalizar_partidos() -> None:
    a = adaptador()
    final, en_juego, programado = a.normalizar(cargar("nfl_games.json")["response"])

    assert final.proveedor_id == "1001"
    assert final.fecha == datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    assert final.temporada == "2026"
    assert final.estatus is EstatusPartido.FINALIZADO
    assert (final.local.nombre, final.visita.nombre) == ("Kansas City Chiefs", "Buffalo Bills")
    assert (final.local.proveedor_id, final.visita.proveedor_id) == ("10", "11")
    assert (final.marcador_local, final.marcador_visita) == (27, 20)
    assert final.jornada is None

    assert en_juego.estatus is EstatusPartido.EN_JUEGO
    assert (en_juego.marcador_local, en_juego.marcador_visita) == (14, 10)
    assert en_juego.local.logo_url is None

    assert programado.estatus is EstatusPartido.PROGRAMADO
    assert programado.marcador_local is None and programado.marcador_visita is None


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("NS", EstatusPartido.PROGRAMADO),
        ("Q1", EstatusPartido.EN_JUEGO),
        ("HT", EstatusPartido.EN_JUEGO),
        ("OT", EstatusPartido.EN_JUEGO),
        ("FT", EstatusPartido.FINALIZADO),
        ("AOT", EstatusPartido.FINALIZADO),
        ("WO", EstatusPartido.FINALIZADO),
        ("PST", EstatusPartido.POSPUESTO),
        ("SUSP", EstatusPartido.POSPUESTO),
        ("CANC", EstatusPartido.CANCELADO),
        ("ABD", EstatusPartido.CANCELADO),
        ("XYZ", EstatusPartido.EN_JUEGO),  # unknown codes are treated as in progress
    ],
)
def test_mapeo_de_estatus(codigo: str, esperado: EstatusPartido) -> None:
    base = cargar("nfl_games.json")["response"][0]
    crudo = base | {"game": base["game"] | {"status": {"short": codigo}}}
    assert adaptador().normalizar([crudo])[0].estatus is esperado


def test_normalizar_partido_sin_marcador_ni_liga() -> None:
    crudo = cargar("nfl_games.json")["response"][0] | {"scores": None, "league": None}
    partido = adaptador().normalizar([crudo])[0]
    assert (partido.marcador_local, partido.marcador_visita) == (None, None)
    assert partido.temporada == "2026"


def test_normalizar_estadisticas_mapea_categorias_y_valida(schemas_dir: str) -> None:
    a = adaptador()
    lineas = a.normalizar_estadisticas("1001", cargar("nfl_players_stats.json")["response"])

    # Players are regrouped from team > category > player; B. Bench never appears in a group.
    por_nombre = {x.jugador.nombre: x for x in lineas}
    assert set(por_nombre) == {
        "Q. Passer",
        "R. Runner",
        "T. Receiver",
        "K. Kicker",
        "D. Defender",
        "N. Blanks",
    }
    assert len(lineas) == 6
    for x in lineas:
        validar_metricas(schemas_dir, a.deporte, x.metricas)
        assert x.minutos is None
        assert x.partido_proveedor_id == "1001"

    passer = por_nombre["Q. Passer"]
    assert passer.equipo_proveedor_id == "10"
    assert passer.jugador.proveedor_id == "3001"
    assert passer.jugador.posicion is None  # the API does not report positions
    assert passer.metricas == {
        "pase": {
            "completos": 24,
            "intentos": 35,
            "yardas": 298,
            "touchdowns": 2,
            "intercepciones": 1,
            "capturas": 3,
        },
        "carrera": {"acarreos": 4, "yardas": 11, "touchdowns": 0, "balonesSueltos": 0},
    }

    runner = por_nombre["R. Runner"]
    assert set(runner.metricas) == {"carrera", "recepcion"}
    assert runner.metricas["carrera"]["acarreos"] == 18
    assert runner.metricas["carrera"]["balonesSueltos"] == 1
    assert runner.metricas["recepcion"] == {
        "objetivos": 4,
        "recepciones": 3,
        "yardas": 27,
        "touchdowns": 0,
    }

    kicker = por_nombre["K. Kicker"]
    assert kicker.metricas == {
        "pateo": {
            "golesCampoAnotados": 2,
            "golesCampoIntentados": 3,
            "puntosExtraAnotados": 4,
            "puntosExtraIntentados": 4,
        }
    }

    defender = por_nombre["D. Defender"]
    assert defender.metricas["defensa"]["capturas"] == 1.5
    assert defender.metricas["defensa"]["tacleadas"] == 6
    assert defender.metricas["defensa"]["pasesDefendidos"] == 1


def test_normalizar_estadisticas_tolera_guiones_y_nulos(schemas_dir: str) -> None:
    a = adaptador()
    blanks = a.normalizar_estadisticas("1001", [linea_de_prueba()])[0]
    assert blanks.metricas["pase"] == {
        "completos": 0,
        "intentos": 0,
        "yardas": 0,
        "touchdowns": 0,
        "intercepciones": 0,
        "capturas": 0,
    }
    # "1-" and "" are not numbers; the receiving line still counts the valid fields.
    assert blanks.metricas["recepcion"] == {
        "objetivos": 2,
        "recepciones": 2,
        "yardas": 0,
        "touchdowns": 0,
    }
    validar_metricas(schemas_dir, a.deporte, blanks.metricas)


def linea_de_prueba() -> dict[str, Any]:
    return linea(
        [
            grupo("Passing", completions_attempts="-", yards=None),
            grupo("Receiving", receptions="2", targets="2", yards="1-", touchdowns=""),
        ],
        "N. Blanks",
    ) | {"player": {"id": 9002, "name": "N. Blanks"}}


def test_valores_numericos_robustos() -> None:
    a = adaptador()
    stats = [
        grupo("Passing", completions_attempts="1,2/3", yards="-12", touchdowns=" 2 ", sacks=True),
        grupo("Defensive", tackles="NaN", sacks="2.5", interceptions=None, passes_defended=3),
    ]
    metricas = a.normalizar_estadisticas("1", [linea(stats)])[0].metricas
    assert metricas["pase"]["completos"] == 0  # "1,2/3" is not a made/attempts pair
    assert metricas["pase"]["intentos"] == 0
    assert metricas["pase"]["yardas"] == -12  # yards may be negative
    assert metricas["pase"]["touchdowns"] == 2
    assert metricas["pase"]["capturas"] == 0  # booleans and negative counts both count as 0
    assert metricas["pase"]["completos"] == 0
    assert metricas["defensa"]["tacleadas"] == 0  # NaN is not a number
    assert metricas["defensa"]["capturas"] == 2.5
    assert metricas["defensa"]["pasesDefendidos"] == 3  # helper spells the key "passes defended"


def test_categoria_defense_y_sin_categorias_reconocidas_se_descarta() -> None:
    a = adaptador()
    solo_defensa = linea([grupo("Defense", tackles=4, sacks=0)])
    sin_mapear = linea([grupo("Punting", punts=5)])
    lineas = a.normalizar_estadisticas("1", [solo_defensa, sin_mapear])
    assert len(lineas) == 1
    assert lineas[0].metricas == {
        "defensa": {
            "tacleadas": 4,
            "capturas": 0.0,
            "intercepciones": 0,
            "pasesDefendidos": 0,
            "balonesForzados": 0,
        }
    }


def test_sin_posicion_ni_lineas() -> None:
    a = adaptador()
    assert a.normalizar_estadisticas("1", []) == []
    sin_posicion = linea([grupo("Kicking", field_goals="1/1")]) | {
        "player": {"id": 9003, "name": "Sin Posicion"}
    }
    assert a.normalizar_estadisticas("1", [sin_posicion])[0].jugador.posicion is None


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("24/35", (24, 35)),
        ("2-3", (2, 3)),
        (" 1 / 2 ", (1, 2)),
        ("-", (0, 0)),
        (None, (0, 0)),
        (7, (0, 0)),
    ],
)
def test_par_de_intentos(valor: Any, esperado: tuple[int, int]) -> None:
    assert _par(valor) == esperado


def test_crear_adaptador_americano_usa_la_temporada_de_settings() -> None:
    settings = Settings(
        database_url="postgresql://x",
        api_sports_key="clave",
        temporada_americano="2027",
        fallback_habilitado=False,
    )
    adaptador_creado = crear_adaptador(Deporte.AMERICANO, settings)
    assert isinstance(adaptador_creado, AdaptadorAmericano)
    assert adaptador_creado.proveedor_liga_id == "1"
    assert adaptador_creado._temporada == "2027"


def test_fecha_se_normaliza_a_utc() -> None:
    base = cargar("nfl_games.json")["response"][0]
    esperado = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    sin_timestamp = base["game"]["date"] | {"timestamp": None}
    for fecha in (sin_timestamp, "2026-11-15T18:00:00", "2026-11-15T12:00:00-06:00"):
        crudo = base | {"game": base["game"] | {"date": fecha}}
        assert adaptador().normalizar([crudo])[0].fecha == esperado


def test_jugador_en_varias_categorias_y_equipos_se_agrupa_por_equipo() -> None:
    a = adaptador()
    lineas = [
        equipo(
            {(1, "Uno"): [grupo("Rushing", carries=2, yards=5), grupo("Receiving", receptions=1)]}
        ),
        equipo({(1, "Uno"): [grupo("Rushing", carries=9, yards=40)]}, team_id=11),
    ]
    resultado = a.normalizar_estadisticas("7", lineas)
    assert [(x.equipo_proveedor_id, set(x.metricas)) for x in resultado] == [
        ("10", {"carrera", "recepcion"}),
        ("11", {"carrera"}),
    ]
