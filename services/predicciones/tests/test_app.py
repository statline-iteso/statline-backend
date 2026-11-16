import pytest
from fastapi.testclient import TestClient

from predicciones.config import Settings
from predicciones.main import create_app, db_disponible, get_settings


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(create_app())


def test_healthz(cliente: TestClient) -> None:
    assert cliente.get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize(("ok", "status"), [(True, 200), (False, 503)])
def test_readyz(ok: bool, status: int) -> None:
    app = create_app()
    app.dependency_overrides[db_disponible] = lambda: ok
    assert TestClient(app).get("/readyz").status_code == status


def test_readyz_sin_database_url() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="")
    assert TestClient(app).get("/readyz").status_code == 503


def test_readyz_con_base_inalcanzable() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://x:y@127.0.0.1:1/z"
    )
    assert TestClient(app).get("/readyz").status_code == 503


def test_metrics(cliente: TestClient) -> None:
    cliente.get("/healthz")
    texto = cliente.get("/metrics").text
    assert "statline_predicciones_requests_total" in texto


@pytest.mark.parametrize(
    ("ruta", "cuerpo"),
    [
        ("/pronosticos/generar", {"deporte": "BASQUETBOL", "jornada": 3}),
        ("/proyecciones/generar", {"deporte": "FUTBOL"}),
        ("/modelos/reentrenar", {"deporte": "AMERICANO", "tipo": "RESULTADO_PARTIDO"}),
    ],
)
def test_rutas_pendientes_responden_501(
    cliente: TestClient, ruta: str, cuerpo: dict[str, object]
) -> None:
    r = cliente.post(ruta, json=cuerpo)
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_valida_el_cuerpo(cliente: TestClient) -> None:
    assert cliente.post("/pronosticos/generar", json={"deporte": "TENIS"}).status_code == 422
