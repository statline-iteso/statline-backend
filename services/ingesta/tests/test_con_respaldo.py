from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx
from conftest import cargar

from ingesta.adaptadores import crear_adaptador
from ingesta.adaptadores.api_sports import (
    ApiSportsError,
    ClienteApiSports,
    CuotaAgotadaError,
    ProveedorCaidoError,
)
from ingesta.adaptadores.balldontlie import BASE_URL as BALLDONTLIE
from ingesta.adaptadores.balldontlie import AdaptadorBalldontlie
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.adaptadores.basquetbol import AdaptadorBasquetbol
from ingesta.adaptadores.con_respaldo import AdaptadorConRespaldo
from ingesta.adaptadores.respaldo import ClienteRespaldo
from ingesta.config import Settings
from ingesta.ejecutor import ejecutar
from ingesta.modelos import Deporte, EquipoNorm, EstadisticaNorm, EstatusPartido, PartidoNorm

APISPORTS = "https://v1.basketball.api-sports.io"


class AdaptadorFalso(AdaptadorDeporte):
    """Scripted adapter: each method either returns a value or raises the next queued error."""

    deporte = Deporte.BASQUETBOL
    proveedor_liga_id = "12"

    def __init__(self, proveedor: str, partidos: list[PartidoNorm] | None = None) -> None:
        self.proveedor = proveedor
        self.partidos = partidos or []
        self.errores_partidos: list[Exception] = []
        self.errores_lineas: list[Exception] = []
        self.llamadas: list[str] = []
        self.peticiones = 0

    def peticiones_usadas(self) -> int:
        return self.peticiones

    def partidos_del_dia(self, fecha: date) -> list[PartidoNorm]:
        self.llamadas.append(f"partidos:{fecha.isoformat()}")
        self.peticiones += 1
        if self.errores_partidos:
            raise self.errores_partidos.pop(0)
        return self.partidos

    def lineas_del_partido(self, pid: str) -> list[EstadisticaNorm]:
        self.llamadas.append(f"lineas:{pid}")
        self.peticiones += 1
        if self.errores_lineas:
            raise self.errores_lineas.pop(0)
        return []

    def obtener_partidos(self, fecha: date) -> list[dict[str, Any]]:
        raise NotImplementedError

    def obtener_estadisticas(self, partido_proveedor_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def normalizar(self, partidos: list[dict[str, Any]]) -> list[PartidoNorm]:
        raise NotImplementedError

    def normalizar_estadisticas(
        self, partido_proveedor_id: str, lineas: list[dict[str, Any]]
    ) -> list[EstadisticaNorm]:
        raise NotImplementedError


def _partido(pid: str) -> PartidoNorm:
    equipo = EquipoNorm("1", "A")
    return PartidoNorm(
        proveedor_id=pid,
        fecha=datetime(2026, 11, 14, tzinfo=UTC),
        temporada="2025-2026",
        estatus=EstatusPartido.FINALIZADO,
        local=equipo,
        visita=EquipoNorm("2", "B"),
    )


def test_cuota_agotada_cambia_al_respaldo_para_el_resto_de_la_corrida() -> None:
    principal = AdaptadorFalso("api-sports")
    principal.errores_partidos = [CuotaAgotadaError("cuota")]
    respaldo = AdaptadorFalso("balldontlie", [_partido("balldontlie:9")])
    a = AdaptadorConRespaldo(principal, respaldo)  # type: ignore[arg-type]

    assert [p.proveedor_id for p in a.partidos_del_dia(date(2026, 11, 14))] == ["balldontlie:9"]
    a.partidos_del_dia(date(2026, 11, 15))

    # The primary is tried once; after the switch it is never called again.
    assert principal.llamadas == ["partidos:2026-11-14"]
    assert respaldo.llamadas == ["partidos:2026-11-14", "partidos:2026-11-15"]
    assert a.proveedor_efectivo() == "api-sports+balldontlie"


def test_5xx_persistente_cambia_al_respaldo() -> None:
    principal = AdaptadorFalso("api-sports")
    principal.errores_partidos = [ProveedorCaidoError("HTTP 500 tras reintentos")]
    a = AdaptadorConRespaldo(principal, AdaptadorFalso("thesportsdb"))  # type: ignore[arg-type]
    a.partidos_del_dia(date(2026, 11, 14))
    assert a.proveedor_efectivo() == "api-sports+thesportsdb"


def test_error_de_4xx_no_cambia_de_proveedor() -> None:
    principal = AdaptadorFalso("api-sports")
    principal.errores_partidos = [ApiSportsError("token inválido")]
    a = AdaptadorConRespaldo(principal, AdaptadorFalso("balldontlie"))  # type: ignore[arg-type]
    with pytest.raises(ApiSportsError, match="token"):
        a.partidos_del_dia(date(2026, 11, 14))
    assert a.proveedor_efectivo() == "api-sports"


def test_sin_fallos_registra_solo_el_principal() -> None:
    a = AdaptadorConRespaldo(AdaptadorFalso("api-sports"), AdaptadorFalso("balldontlie"))  # type: ignore[arg-type]
    a.partidos_del_dia(date(2026, 11, 14))
    assert a.proveedor_efectivo() == "api-sports"


def test_partido_del_principal_sin_estadisticas_tras_cambiar() -> None:
    principal = AdaptadorFalso("api-sports")
    principal.errores_lineas = [CuotaAgotadaError("cuota")]
    respaldo = AdaptadorFalso("balldontlie")
    a = AdaptadorConRespaldo(principal, respaldo)  # type: ignore[arg-type]

    assert a.lineas_del_partido("414001") == []  # the primary's id is unknown to the fallback
    assert respaldo.llamadas == []
    assert a.proveedor_efectivo() == "api-sports+balldontlie"


def test_partido_del_respaldo_va_siempre_al_respaldo() -> None:
    principal = AdaptadorFalso("api-sports")
    respaldo = AdaptadorFalso("balldontlie")
    a = AdaptadorConRespaldo(principal, respaldo)  # type: ignore[arg-type]
    a.lineas_del_partido("balldontlie:9")
    assert respaldo.llamadas == ["lineas:balldontlie:9"]
    assert principal.llamadas == []


class RepoFalso:
    def __init__(self) -> None:
        self.partidos: list[PartidoNorm] = []
        self.final: dict[str, Any] = {}

    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str:
        # The seeded liga row is the API-Sports one, whatever provider fed the run.
        assert (proveedor, proveedor_liga_id) == ("api-sports", "12")
        return "liga-nba"

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
        pass


@respx.mock
def test_corrida_real_pasa_a_balldontlie_tras_error_persistente_5xx(schemas_dir: str) -> None:
    respx.get(f"{APISPORTS}/games").mock(return_value=httpx.Response(500))
    respx.get(f"{BALLDONTLIE}/games").mock(
        return_value=httpx.Response(200, json=cargar("balldontlie_games.json"))
    )
    respx.get(f"{BALLDONTLIE}/stats").mock(
        return_value=httpx.Response(200, json=cargar("balldontlie_stats.json"))
    )
    principal = AdaptadorBasquetbol(
        ClienteApiSports("basketball", "clave", backoff_s=0, max_retries=1), "2025-2026"
    )
    respaldo = AdaptadorBalldontlie(ClienteRespaldo(BALLDONTLIE, backoff_s=0), "2025-2026")
    repo = RepoFalso()

    resultado = ejecutar(
        AdaptadorConRespaldo(principal, respaldo),  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        desde=date(2026, 11, 14),
        hasta=date(2026, 11, 14),
        schemas_dir=schemas_dir,
    )

    assert resultado.exitosa and resultado.error is None
    assert [p.proveedor_id for p in repo.partidos] == ["balldontlie:90001", "balldontlie:90002"]
    assert resultado.estadisticas == 2  # DNP dropped
    assert repo.final["proveedor"] == "api-sports+balldontlie"
    # Two failed attempts on the primary (1 + 1 retry) before the switch, then the fallback calls.
    assert principal.peticiones_usadas() == 2
    assert repo.final["peticiones"] == 2 + respaldo.peticiones_usadas()


def _settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"database_url": "postgresql://x", "api_sports_key": "clave"}
    return Settings(**(base | kw))  # type: ignore[arg-type]


def test_crear_adaptador_sin_clave_balldontlie_no_tiene_respaldo_nba() -> None:
    settings = _settings(balldontlie_api_key="")
    assert isinstance(crear_adaptador(Deporte.BASQUETBOL, settings), AdaptadorBasquetbol)


def test_crear_adaptador_con_clave_envuelve_el_principal() -> None:
    settings = _settings(balldontlie_api_key="clave-bdl")
    adaptador = crear_adaptador(Deporte.BASQUETBOL, settings)
    assert isinstance(adaptador, AdaptadorConRespaldo)
    assert adaptador.proveedor == "api-sports"
    assert adaptador.proveedor_liga_id == "12"


def test_fallback_deshabilitado_devuelve_solo_el_principal() -> None:
    settings = _settings(balldontlie_api_key="clave-bdl", fallback_habilitado=False)
    assert isinstance(crear_adaptador(Deporte.BASQUETBOL, settings), AdaptadorBasquetbol)


def test_nfl_y_liga_mx_tienen_respaldo_thesportsdb_sin_clave_propia() -> None:
    nfl = crear_adaptador(Deporte.AMERICANO, _settings())
    futbol = crear_adaptador(Deporte.FUTBOL, _settings())
    assert isinstance(nfl, AdaptadorConRespaldo) and isinstance(futbol, AdaptadorConRespaldo)
    assert nfl.proveedor_liga_id == "1"
    assert futbol.proveedor_liga_id == "262"
