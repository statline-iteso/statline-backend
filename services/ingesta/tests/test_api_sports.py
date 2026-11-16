import httpx
import pytest
import respx

from ingesta.adaptadores.api_sports import ApiSportsError, ClienteApiSports, CuotaAgotadaError

BASE = "https://v1.basketball.api-sports.io"


def cliente(**kw: object) -> ClienteApiSports:
    return ClienteApiSports("basketball", "clave-de-prueba", backoff_s=0, **kw)  # type: ignore[arg-type]


@respx.mock
def test_envia_la_llave_y_devuelve_response() -> None:
    ruta = respx.get(f"{BASE}/games").mock(
        return_value=httpx.Response(200, json={"errors": [], "response": [{"id": 1}]})
    )
    c = cliente()
    assert c.get("/games", {"date": "2026-11-14"}) == [{"id": 1}]
    assert ruta.calls[0].request.headers["x-apisports-key"] == "clave-de-prueba"
    assert c.peticiones == 1


@respx.mock
def test_reintenta_429_y_5xx() -> None:
    respx.get(f"{BASE}/games").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json={"errors": [], "response": []}),
        ]
    )
    c = cliente(max_retries=3)
    assert c.get("/games", {}) == []
    assert c.peticiones == 3


@respx.mock
def test_falla_tras_agotar_reintentos() -> None:
    respx.get(f"{BASE}/games").mock(return_value=httpx.Response(500))
    with pytest.raises(ApiSportsError, match="tras reintentos"):
        cliente(max_retries=1).get("/games", {})


@respx.mock
def test_no_reintenta_4xx() -> None:
    respx.get(f"{BASE}/games").mock(return_value=httpx.Response(403))
    c = cliente()
    with pytest.raises(ApiSportsError, match="403"):
        c.get("/games", {})
    assert c.peticiones == 1


@respx.mock
def test_errors_en_200_es_error() -> None:
    respx.get(f"{BASE}/games").mock(
        return_value=httpx.Response(200, json={"errors": {"token": "invalid"}, "response": []})
    )
    with pytest.raises(ApiSportsError, match="token"):
        cliente().get("/games", {})


@respx.mock
def test_error_de_red_se_reintenta() -> None:
    respx.get(f"{BASE}/games").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ApiSportsError, match="boom"):
        cliente(max_retries=1).get("/games", {})


@respx.mock
def test_respeta_la_cuota() -> None:
    respx.get(f"{BASE}/games").mock(
        return_value=httpx.Response(200, json={"errors": [], "response": []})
    )
    c = cliente(cuota=2)
    c.get("/games", {})
    c.get("/games", {})
    with pytest.raises(CuotaAgotadaError):
        c.get("/games", {})
    c.close()
