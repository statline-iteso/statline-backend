import copy
from datetime import date
from typing import Any

from conftest import cargar
from test_futbol import ClienteFalso

from ingesta.adaptadores.futbol import AdaptadorFutbol
from ingesta.ejecutor import ejecutar
from ingesta.modelos import Deporte, EstadisticaNorm, PartidoNorm


class RepoFalso:
    def __init__(self) -> None:
        self.partidos: list[PartidoNorm] = []
        self.estadisticas: list[EstadisticaNorm] = []
        self.final: dict[str, Any] = {}

    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str:
        assert (deporte, proveedor, proveedor_liga_id) == (Deporte.FUTBOL, "api-sports", "262")
        return "liga-mx"

    def iniciar_ejecucion(self, deporte: Deporte, proveedor: str) -> str:
        return "ejec-1"

    def finalizar_ejecucion(self, ejecucion_id: str, **kw: Any) -> None:
        self.final = {"id": ejecucion_id, **kw}

    def guardar_partido(self, liga_id: str, partido: PartidoNorm) -> str:
        self.partidos.append(partido)
        return f"partido-{partido.proveedor_id}"

    def guardar_estadistica(
        self, deporte: Deporte, liga_id: str, partido_id: str, linea: EstadisticaNorm
    ) -> None:
        self.estadisticas.append(linea)


def test_corrida_liga_mx_guarda_partidos_y_lineas_validas(schemas_dir: str) -> None:
    repo, cliente = RepoFalso(), ClienteFalso()
    adaptador = AdaptadorFutbol(cliente, "2026")  # type: ignore[arg-type]

    r = ejecutar(
        adaptador,
        repo,  # type: ignore[arg-type]
        desde=date(2026, 11, 14),
        hasta=date(2026, 11, 14),
        schemas_dir=schemas_dir,
    )

    assert r.exitosa and r.error is None
    assert r.partidos == 3  # final, scheduled and postponed
    assert r.estadisticas == 4  # box score only for the FT game; substitutes dropped
    assert r.descartadas == 0
    assert repo.final["peticiones"] == 2
    assert [p.proveedor_id for p in repo.partidos] == ["1208001", "1208002", "1208003"]


def test_linea_invalida_se_descarta_y_no_detiene_la_corrida(schemas_dir: str) -> None:
    repo = RepoFalso()
    jugadores = copy.deepcopy(cargar("ligamx_players.json")["response"])
    # Three yellow cards in one match is outside futbol.schema.json (max 2): skipped and counted.
    jugadores[0]["players"][1]["statistics"][0]["cards"]["yellow"] = 3
    cliente = ClienteFalso(partidos=cargar("ligamx_fixtures.json")["response"][:1])
    cliente_jugadores = cliente.get

    def get(path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if path == "/fixtures/players":
            return copy.deepcopy(jugadores)
        return cliente_jugadores(path, params)

    cliente.get = get  # type: ignore[method-assign]
    adaptador = AdaptadorFutbol(cliente, "2026")  # type: ignore[arg-type]

    r = ejecutar(
        adaptador,
        repo,  # type: ignore[arg-type]
        desde=date(2026, 11, 14),
        hasta=date(2026, 11, 14),
        schemas_dir=schemas_dir,
    )

    assert r.exitosa
    assert r.descartadas == 1
    assert r.estadisticas == 3
    assert "M. Prueba" not in [linea.jugador.nombre for linea in repo.estadisticas]
