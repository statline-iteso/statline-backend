from datetime import date
from typing import Any

from test_basquetbol import ClienteFalso

from ingesta.adaptadores.api_sports import CuotaAgotadaError
from ingesta.adaptadores.basquetbol import AdaptadorBasquetbol
from ingesta.ejecutor import ejecutar
from ingesta.modelos import Deporte, EstadisticaNorm, PartidoNorm
from ingesta.repositorio import LigaNoSembradaError


class RepoFalso:
    def __init__(self, *, liga: bool = True) -> None:
        self.liga = liga
        self.partidos: list[PartidoNorm] = []
        self.estadisticas: list[EstadisticaNorm] = []
        self.final: dict[str, Any] = {}

    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str:
        if not self.liga:
            raise LigaNoSembradaError("sin liga")
        assert (deporte, proveedor, proveedor_liga_id) == (Deporte.BASQUETBOL, "api-sports", "12")
        return "liga-1"

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


def correr(repo: RepoFalso, cliente: ClienteFalso, schemas_dir: str, dias: int = 1) -> Any:
    adaptador = AdaptadorBasquetbol(cliente, "2025-2026")  # type: ignore[arg-type]
    return ejecutar(
        adaptador,
        repo,  # type: ignore[arg-type]
        desde=date(2026, 11, 14),
        hasta=date(2026, 11, 13 + dias),
        schemas_dir=schemas_dir,
    )


def test_corrida_exitosa_guarda_partidos_y_solo_box_scores_de_finales(schemas_dir: str) -> None:
    repo, cliente = RepoFalso(), ClienteFalso()
    r = correr(repo, cliente, schemas_dir)

    assert r.exitosa and r.error is None
    assert r.partidos == 2  # final + scheduled
    assert r.estadisticas == 2  # only the final game's lines, DNP dropped
    # 1 request for games + 1 for the finished game's box score
    assert repo.final == {
        "id": "ejec-1",
        "exitosa": True,
        "registros": 4,
        "peticiones": 2,
        "proveedor": "api-sports",
        "error": None,
    }


def test_recorre_cada_dia_del_rango(schemas_dir: str) -> None:
    repo, cliente = RepoFalso(), ClienteFalso()
    correr(repo, cliente, schemas_dir, dias=2)
    fechas = [p["date"] for path, p in cliente.llamadas if path == "/games"]
    assert fechas == ["2026-11-14", "2026-11-15"]


def test_lineas_invalidas_se_descartan(schemas_dir: str, monkeypatch: Any) -> None:
    repo, cliente = RepoFalso(), ClienteFalso()
    original = AdaptadorBasquetbol.normalizar_estadisticas

    def con_basura(self: AdaptadorBasquetbol, pid: str, lineas: Any) -> list[EstadisticaNorm]:
        buenas = original(self, pid, lineas)
        mala = EstadisticaNorm(pid, "140", buenas[0].jugador, 10, {"puntos": -5})
        return [*buenas, mala]

    monkeypatch.setattr(AdaptadorBasquetbol, "normalizar_estadisticas", con_basura)
    r = correr(repo, cliente, schemas_dir)
    assert r.exitosa
    assert (r.estadisticas, r.descartadas) == (2, 1)


def test_liga_no_sembrada_marca_fallida(schemas_dir: str) -> None:
    repo = RepoFalso(liga=False)
    r = correr(repo, ClienteFalso(), schemas_dir)
    assert not r.exitosa
    assert r.error is not None and "LigaNoSembradaError" in r.error
    assert repo.final["exitosa"] is False


def test_cuota_agotada_conserva_lo_guardado(schemas_dir: str) -> None:
    class ClienteConCuota(ClienteFalso):
        def get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            if path != "/games":
                raise CuotaAgotadaError("cuota de 1 peticiones agotada")
            return super().get(path, params)

    repo = RepoFalso()
    r = correr(repo, ClienteConCuota(), schemas_dir)
    assert not r.exitosa
    assert r.error == "cuota de 1 peticiones agotada"
    assert len(repo.partidos) == 1  # the final game was stored before the quota ran out
