from datetime import date
from typing import Any

import pytest

from ingesta import cli
from ingesta.modelos import Deporte
from ingesta.repositorio import LigaNoSembradaError


class RepoFalso:
    def __init__(self, *, liga: bool = True) -> None:
        self.liga = liga
        self.ejecuciones: list[tuple[Deporte, str]] = []
        self.partidos = 0
        self.estadisticas = 0
        self.finales: list[dict[str, Any]] = []

    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str:
        if not self.liga:
            raise LigaNoSembradaError("sin liga")
        assert proveedor == "api-sports"
        return "liga-1"

    def iniciar_ejecucion(self, deporte: Deporte, proveedor: str) -> str:
        self.ejecuciones.append((deporte, proveedor))
        return f"ejec-{len(self.ejecuciones)}"

    def finalizar_ejecucion(self, ejecucion_id: str, **kw: Any) -> None:
        self.finales.append({"id": ejecucion_id, **kw})

    def guardar_partido(self, liga_id: str, partido: Any) -> str:
        self.partidos += 1
        return f"partido-{self.partidos}"

    def guardar_estadistica(
        self, deporte: Deporte, liga_id: str, partido_id: str, linea: Any
    ) -> None:
        self.estadisticas += 1


@pytest.fixture
def entorno(monkeypatch: pytest.MonkeyPatch, schemas_dir: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("API_SPORTS_KEY", "no-usada")
    monkeypatch.setenv("SCHEMAS_DIR", schemas_dir)


def conectar_con(monkeypatch: pytest.MonkeyPatch, repo: RepoFalso) -> None:
    monkeypatch.setattr(cli.RepositorioPostgres, "conectar", classmethod(lambda cls, url: repo))


def test_sin_confirmar_no_toca_la_base(monkeypatch: pytest.MonkeyPatch, entorno: None) -> None:
    def no_debe_conectar(cls: object, url: str) -> None:
        raise AssertionError("no debe conectar sin --confirmar")

    monkeypatch.setattr(cli.RepositorioPostgres, "conectar", classmethod(no_debe_conectar))
    assert cli.main(["seed-demo", "--deportes", "futbol"]) == 2


def test_confirmar_siembra_cada_deporte_con_proveedor_demo(
    monkeypatch: pytest.MonkeyPatch, entorno: None
) -> None:
    repo = RepoFalso()
    conectar_con(monkeypatch, repo)
    codigo = cli.main(
        ["seed-demo", "--deportes", "futbol,basquetbol", "--dias", "5", "--confirmar"]
    )
    assert codigo == 0
    assert repo.ejecuciones == [(Deporte.FUTBOL, "demo"), (Deporte.BASQUETBOL, "demo")]
    assert [f["exitosa"] for f in repo.finales] == [True, True]
    assert all(f["peticiones"] == 0 for f in repo.finales)
    assert repo.partidos > 0 and repo.estadisticas > 0


def test_liga_no_sembrada_marca_la_ejecucion_fallida(
    monkeypatch: pytest.MonkeyPatch, entorno: None
) -> None:
    repo = RepoFalso(liga=False)
    conectar_con(monkeypatch, repo)
    assert cli.main(["seed-demo", "--deportes", "americano", "--confirmar"]) == 1
    assert repo.finales[0]["exitosa"] is False
    assert "LigaNoSembradaError" in repo.finales[0]["error"]


def test_deporte_desconocido_es_error_de_argumentos(entorno: None) -> None:
    with pytest.raises(SystemExit):
        cli.main(["seed-demo", "--deportes", "tenis", "--confirmar"])


def test_dias_no_positivos_es_error_de_argumentos(entorno: None) -> None:
    with pytest.raises(SystemExit):
        cli.main(["seed-demo", "--dias", "0", "--confirmar"])


def test_semilla_y_fecha_de_referencia_se_pasan_al_generador(
    monkeypatch: pytest.MonkeyPatch, entorno: None
) -> None:
    repo = RepoFalso()
    conectar_con(monkeypatch, repo)
    capturados: list[dict[str, Any]] = []
    original = cli.sembrar

    def espia(*args: Any, **kw: Any) -> Any:
        capturados.append(kw)
        return original(*args, **kw)

    monkeypatch.setattr(cli, "sembrar", espia)
    cli.main(["seed-demo", "--deportes", "futbol", "--semilla", "9", "--dias", "3", "--confirmar"])
    assert capturados[0]["semilla"] == 9
    assert capturados[0]["dias"] == 3
    assert isinstance(capturados[0]["hoy"], date)
    assert capturados[0]["temporada"] == "2026"
