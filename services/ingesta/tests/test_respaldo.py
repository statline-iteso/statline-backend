import httpx
import pytest
import respx

from ingesta.adaptadores.api_sports import ProveedorCaidoError
from ingesta.adaptadores.respaldo import (
    ClienteRespaldo,
    RespuestaRespaldoError,
    paginar_cursor,
    prefijar,
    quitar_prefijo,
)

BASE = "https://respaldo.test/v1"


def cliente(**kw: object) -> ClienteRespaldo:
    return ClienteRespaldo(BASE, backoff_s=0, **kw)  # type: ignore[arg-type]


@respx.mock
def test_envia_cabeceras_y_cuenta_peticiones() -> None:
    ruta = respx.get(f"{BASE}/games").mock(return_value=httpx.Response(200, json={"data": []}))
    c = ClienteRespaldo(BASE, headers={"Authorization": "clave"}, backoff_s=0)
    assert c.get("/games", {"dates[]": "2026-11-14"}) == {"data": []}
    assert ruta.calls[0].request.headers["Authorization"] == "clave"
    assert c.peticiones == 1


@respx.mock
def test_reintenta_429_y_5xx_y_luego_responde() -> None:
    respx.get(f"{BASE}/games").mock(
        side_effect=[httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"a": 1})]
    )
    c = cliente(max_retries=3)
    assert c.get("/games") == {"a": 1}
    assert c.peticiones == 3


@respx.mock
def test_error_persistente_5xx_es_proveedor_caido() -> None:
    respx.get(f"{BASE}/games").mock(return_value=httpx.Response(500))
    with pytest.raises(ProveedorCaidoError, match="tras reintentos"):
        cliente(max_retries=1).get("/games")


@respx.mock
def test_error_de_red_persistente_es_proveedor_caido() -> None:
    respx.get(f"{BASE}/games").mock(side_effect=httpx.ConnectError("sin red"))
    with pytest.raises(ProveedorCaidoError, match="sin red"):
        cliente(max_retries=1).get("/games")


@respx.mock
def test_4xx_no_reintenta_y_no_es_caida() -> None:
    respx.get(f"{BASE}/games").mock(return_value=httpx.Response(401))
    c = cliente()
    with pytest.raises(RespuestaRespaldoError, match="401"):
        c.get("/games")
    assert c.peticiones == 1


@respx.mock
def test_cuerpo_que_no_es_objeto_es_error() -> None:
    respx.get(f"{BASE}/games").mock(return_value=httpx.Response(200, json=[1, 2]))
    with pytest.raises(RespuestaRespaldoError):
        cliente().get("/games")


@respx.mock
def test_retry_after_se_respeta_y_se_limita(monkeypatch: pytest.MonkeyPatch) -> None:
    esperas: list[float] = []
    monkeypatch.setattr("ingesta.adaptadores.respaldo.time.sleep", esperas.append)
    respx.get(f"{BASE}/games").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429, headers={"Retry-After": "9999"}),
            httpx.Response(200, json={}),
        ]
    )
    cliente(max_retries=3).get("/games")
    assert esperas == [7.0, 60.0]


@respx.mock
def test_pagina_por_cursor_hasta_next_cursor_nulo() -> None:
    ruta = respx.get(f"{BASE}/stats").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"n": 1}], "meta": {"next_cursor": 50}}),
            httpx.Response(200, json={"data": [{"n": 2}], "meta": {"next_cursor": None}}),
        ]
    )
    datos = paginar_cursor(cliente(), "/stats", {"game_ids[]": "9"})
    assert datos == [{"n": 1}, {"n": 2}]
    segunda = ruta.calls[1].request.url.params
    assert segunda["cursor"] == "50"
    assert segunda["per_page"] == "100"


@respx.mock
def test_paginacion_con_cursor_que_no_avanza_se_corta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingesta.adaptadores.respaldo.MAX_PAGINAS", 3)
    respx.get(f"{BASE}/games").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"next_cursor": 1}})
    )
    with pytest.raises(RespuestaRespaldoError, match="páginas"):
        paginar_cursor(cliente(), "/games", {})


def test_ids_con_prefijo() -> None:
    assert prefijar("balldontlie", 42) == "balldontlie:42"
    assert quitar_prefijo("balldontlie", "balldontlie:42") == "42"
    assert quitar_prefijo("balldontlie", "42") == "42"
