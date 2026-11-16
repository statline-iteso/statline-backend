from datetime import UTC, date, datetime
from typing import Any

from conftest import cargar

from ingesta.adaptadores.basquetbol import AdaptadorBasquetbol
from ingesta.modelos import EstatusPartido
from ingesta.validacion import validar_metricas


class ClienteFalso:
    def __init__(self) -> None:
        self.peticiones = 0
        self.llamadas: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.peticiones += 1
        self.llamadas.append((path, params))
        nombre = "nba_games.json" if path == "/games" else "nba_players.json"
        respuesta: list[dict[str, Any]] = cargar(nombre)["response"]
        return respuesta


def adaptador() -> tuple[AdaptadorBasquetbol, ClienteFalso]:
    cliente = ClienteFalso()
    return AdaptadorBasquetbol(cliente, "2025-2026"), cliente  # type: ignore[arg-type]


def test_obtener_usa_liga_temporada_y_fecha() -> None:
    a, c = adaptador()
    a.obtener_partidos(date(2026, 11, 14))
    a.obtener_estadisticas("414001")
    assert c.llamadas == [
        ("/games", {"league": "12", "season": "2025-2026", "date": "2026-11-14"}),
        ("/games/statistics/players", {"id": "414001"}),
    ]
    assert a.peticiones_usadas() == 2


def test_normalizar_partidos() -> None:
    a, _ = adaptador()
    final, programado = a.normalizar(cargar("nba_games.json")["response"])

    assert final.proveedor_id == "414001"
    assert final.fecha == datetime(2026, 11, 14, 0, 30, tzinfo=UTC)
    assert final.estatus is EstatusPartido.FINALIZADO
    assert (final.local.nombre, final.visita.nombre) == ("Denver Nuggets", "Los Angeles Lakers")
    assert (final.marcador_local, final.marcador_visita) == (118, 111)

    assert programado.estatus is EstatusPartido.PROGRAMADO
    assert programado.marcador_local is None


def test_normalizar_estadisticas_descarta_dnp_y_valida(schemas_dir: str) -> None:
    a, _ = adaptador()
    lineas = a.normalizar_estadisticas("414001", cargar("nba_players.json")["response"])

    assert [linea.jugador.nombre for linea in lineas] == ["N. Jokic", "L. James"]
    jokic = lineas[0]
    assert jokic.minutos == 36
    assert jokic.equipo_proveedor_id == "140"
    assert jokic.metricas["puntos"] == 31
    assert jokic.metricas["rebotes"] == 14
    assert jokic.metricas["triplesIntentados"] == 4
    for linea in lineas:
        validar_metricas(schemas_dir, a.deporte, linea.metricas)


def test_normalizar_estadisticas_vacias() -> None:
    a, _ = adaptador()
    assert a.normalizar_estadisticas("1", []) == []
    crudas = cargar("nba_players.json")["response"]
    dnp = [linea for linea in crudas if linea["minutes"] is None]
    assert a.normalizar_estadisticas("1", dnp) == []


def test_estatus_desconocido_es_en_juego() -> None:
    a, _ = adaptador()
    crudo = cargar("nba_games.json")["response"][0] | {"status": {"short": "Q3"}}
    assert a.normalizar([crudo])[0].estatus is EstatusPartido.EN_JUEGO
