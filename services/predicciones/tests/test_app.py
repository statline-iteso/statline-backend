import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fabrica import generar_datos
from fastapi.testclient import TestClient

from predicciones import datos, registro
from predicciones.config import Settings
from predicciones.errores import (
    ArtefactoInvalidoError,
    DatosInsuficientesError,
    ModeloNoEncontradoError,
    SinModeloActivoError,
)
from predicciones.main import create_app, db_disponible, get_conn, get_settings
from predicciones.modelos.jugador import entrenar_jugador
from predicciones.modelos.resultado import entrenar_resultado
from predicciones.registro import ModeloCargado
from predicciones.schemas import Deporte

MODELO_ID = str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))


@pytest.fixture(scope="module")
def bundle_resultado() -> tuple[Any, Any, Any]:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=200, seed=3)
    bundle = entrenar_resultado(Deporte.BASQUETBOL, partidos).bundle
    programados = partidos.tail(4).copy()
    programados[["marcador_local", "marcador_visita"]] = float("nan")
    historial = partidos.iloc[:-4]
    return bundle, historial, programados


@pytest.fixture(scope="module")
def bundle_jugador() -> tuple[Any, Any, Any, Any]:
    partidos, lineas = generar_datos(Deporte.BASQUETBOL, partidos=120, seed=5)
    bundle = entrenar_jugador(Deporte.BASQUETBOL, lineas, estimadores=20).bundle
    programados = partidos.tail(2).copy()
    programados[["marcador_local", "marcador_visita"]] = float("nan")
    ids = set(programados["partido_id"])
    historial = lineas[~lineas["partido_id"].isin(ids)]
    jugadores = lineas[["jugador_id", "equipo_id"]].drop_duplicates("jugador_id")
    return bundle, historial, programados, jugadores


@pytest.fixture
def cliente(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://fake", artefactos_dir=str(tmp_path)
    )
    app.dependency_overrides[get_conn] = lambda: object()
    yield TestClient(app)


def _activo(bundle: Any) -> ModeloCargado:
    return ModeloCargado(MODELO_ID, "20260101000000", "a" * 64, bundle)


def test_healthz() -> None:
    assert TestClient(create_app()).get("/healthz").json() == {"status": "ok"}


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


def test_metrics() -> None:
    cliente = TestClient(create_app())
    cliente.get("/healthz")
    assert "statline_predicciones_requests_total" in cliente.get("/metrics").text


def test_valida_el_cuerpo_con_error_de_forma_uniforme(cliente: TestClient) -> None:
    r = cliente.post("/pronosticos/generar", json={"deporte": "TENIS"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"]


def test_pronosticos_generar_escribe_y_responde_camel_case(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch, bundle_resultado: Any
) -> None:
    bundle, historial, programados = bundle_resultado
    escritos: list[tuple[str, list[dict[str, Any]]]] = []
    monkeypatch.setattr(registro, "cargar_activo", lambda *a, **k: _activo(bundle))
    monkeypatch.setattr(datos, "cargar_partidos", lambda *a: historial)
    monkeypatch.setattr(datos, "cargar_partidos_programados", lambda *a: programados)
    monkeypatch.setattr(
        datos, "reemplazar_pronosticos", lambda _c, mid, filas: escritos.append((mid, list(filas)))
    )
    r = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["deporte"] == "BASQUETBOL"
    assert cuerpo["modeloId"] == MODELO_ID
    assert cuerpo["generados"] == 4
    primero = cuerpo["pronosticos"][0]
    assert set(primero) == {
        "id",
        "partidoId",
        "probLocal",
        "probEmpate",
        "probVisita",
        "marcadorEsperadoLocal",
        "marcadorEsperadoVisita",
    }
    assert primero["probEmpate"] == 0.0  # NBA has no draws
    assert escritos[0][0] == MODELO_ID and len(escritos[0][1]) == 4


def test_pronosticos_filtra_por_jornada_y_partido(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch, bundle_resultado: Any
) -> None:
    bundle, historial, programados = bundle_resultado
    monkeypatch.setattr(registro, "cargar_activo", lambda *a, **k: _activo(bundle))
    monkeypatch.setattr(datos, "cargar_partidos", lambda *a: historial)
    monkeypatch.setattr(datos, "cargar_partidos_programados", lambda *a: programados)
    monkeypatch.setattr(datos, "reemplazar_pronosticos", lambda *a: None)
    unica = str(programados["partido_id"].iloc[1])
    r = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL", "partido_ids": [unica]})
    assert r.json()["generados"] == 1
    assert r.json()["pronosticos"][0]["partidoId"] == unica
    sin = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL", "jornada": 999})
    assert sin.json()["generados"] == 0


def test_pronosticos_sin_modelo_activo_es_409(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_activo(*_a: Any, **_k: Any) -> None:
        raise SinModeloActivoError("no hay modelo activo")

    monkeypatch.setattr(registro, "cargar_activo", sin_activo)
    r = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NO_ACTIVE_MODEL"


def test_proyecciones_generar_con_metricas_por_objetivo(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch, bundle_jugador: Any
) -> None:
    bundle, historial, programados, jugadores = bundle_jugador
    escritos: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(registro, "cargar_activo", lambda *a, **k: _activo(bundle))
    monkeypatch.setattr(datos, "cargar_lineas", lambda *a: historial)
    monkeypatch.setattr(datos, "cargar_partidos_programados", lambda *a: programados)
    monkeypatch.setattr(datos, "cargar_jugadores", lambda *a: jugadores)
    monkeypatch.setattr(datos, "reemplazar_proyecciones", lambda _c, _m, f: escritos.append(f))
    r = cliente.post("/proyecciones/generar", json={"deporte": "BASQUETBOL"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["generados"] == len(cuerpo["proyecciones"]) > 0
    assert set(cuerpo["proyecciones"][0]["metricas"]) == {"puntos", "rebotes", "asistencias"}
    assert len(escritos[0]) == cuerpo["generados"]


def test_precision_resultado(cliente: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    info = {
        "id": MODELO_ID,
        "version": "v1",
        "nombre_metrica": "log_loss",
        "metrica_error": 0.6,
    }
    filas = [
        {
            "prob_local": 0.9,
            "prob_empate": 0.0,
            "prob_visita": 0.1,
            "marcador_local": 100,
            "marcador_visita": 90,
        }
    ]
    monkeypatch.setattr(datos, "cargar_info_modelo_activo", lambda *a: info)
    monkeypatch.setattr(datos, "cargar_pronosticos_resueltos", lambda *a: filas)
    r = cliente.get("/precision", params={"deporte": "BASQUETBOL", "tipo": "RESULTADO_PARTIDO"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["modelo"] == {
        "id": MODELO_ID,
        "version": "v1",
        "nombreMetrica": "log_loss",
        "metricaError": 0.6,
    }
    assert cuerpo["precision"]["n"] == 1
    assert cuerpo["precision"]["accuracy"] == 1.0


def test_precision_proyeccion(cliente: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    info = {"id": MODELO_ID, "version": "v1", "nombre_metrica": "mae", "metrica_error": 4.0}
    filas = [{"proyeccion": {"puntos": 10.0}, "estadistica": {"puntos": 14, "rebotes": 3}}]
    monkeypatch.setattr(datos, "cargar_info_modelo_activo", lambda *a: info)
    monkeypatch.setattr(datos, "cargar_proyecciones_resueltas", lambda *a: filas)
    r = cliente.get("/precision", params={"deporte": "BASQUETBOL", "tipo": "PROYECCION_JUGADOR"})
    assert r.status_code == 200
    assert r.json()["precision"]["porObjetivo"]["puntos"] == {"n": 1, "mae": 4.0}


def test_precision_sin_modelo_activo_es_409(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sin_activo(*_a: Any) -> None:
        raise SinModeloActivoError("no hay modelo activo")

    monkeypatch.setattr(datos, "cargar_info_modelo_activo", sin_activo)
    r = cliente.get("/precision", params={"deporte": "FUTBOL", "tipo": "RESULTADO_PARTIDO"})
    assert r.status_code == 409


def test_precision_exige_deporte_y_tipo(cliente: TestClient) -> None:
    r = cliente.get("/precision", params={"deporte": "FUTBOL"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reentrenar_responde_el_resumen(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    resumen = {
        "modelo_id": MODELO_ID,
        "version": "v2",
        "deporte": "BASQUETBOL",
        "tipo": "RESULTADO_PARTIDO",
        "nombre_metrica": "log_loss",
        "metrica": 0.61,
        "baseline": 0.69,
        "n_train": 100,
        "n_test": 25,
        "activado": True,
        "motivo": "primer modelo que supera el baseline",
    }
    monkeypatch.setattr(registro, "entrenar_y_registrar", lambda *a, **k: resumen)
    r = cliente.post(
        "/modelos/reentrenar", json={"deporte": "BASQUETBOL", "tipo": "RESULTADO_PARTIDO"}
    )
    assert r.status_code == 200
    assert r.json()["nTrain"] == 100
    assert r.json()["activado"] is True


def test_reentrenar_con_pocos_datos_es_422(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def pocos(*_a: Any, **_k: Any) -> None:
        raise DatosInsuficientesError("pocos partidos")

    monkeypatch.setattr(registro, "entrenar_y_registrar", pocos)
    r = cliente.post(
        "/modelos/reentrenar", json={"deporte": "FUTBOL", "tipo": "PROYECCION_JUGADOR"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_DATA"


def test_activar_es_forzado_y_responde_ok(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []
    monkeypatch.setattr(registro, "activar", lambda _c, mid: llamadas.append(mid))
    r = cliente.post(f"/modelos/{MODELO_ID.upper()}/activar")
    assert r.status_code == 200
    assert r.json() == {"modeloId": MODELO_ID, "activo": True}
    assert llamadas == [MODELO_ID]


def test_activar_modelo_inexistente_o_id_invalido_es_404(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_existe(*_a: Any) -> None:
        raise ModeloNoEncontradoError("x")

    monkeypatch.setattr(registro, "activar", no_existe)
    assert cliente.post(f"/modelos/{MODELO_ID}/activar").status_code == 404
    assert cliente.post("/modelos/no-es-uuid/activar").status_code == 404


def test_artefacto_invalido_es_500_con_codigo(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def malo(*_a: Any, **_k: Any) -> None:
        raise ArtefactoInvalidoError("sha256 no coincide")

    monkeypatch.setattr(registro, "cargar_activo", malo)
    r = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL"})
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "ARTEFACTO_INVALIDO"


def test_sin_database_url_es_503() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="")
    r = TestClient(app).post("/pronosticos/generar", json={"deporte": "BASQUETBOL"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_base_inalcanzable_es_503() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://x:y@127.0.0.1:1/z"
    )
    r = TestClient(app).get("/precision", params={"deporte": "FUTBOL", "tipo": "RESULTADO_PARTIDO"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_error_operacional_durante_la_consulta_es_503(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def caida(*_a: Any) -> None:
        raise psycopg.OperationalError("conexión perdida")

    monkeypatch.setattr(datos, "cargar_info_modelo_activo", caida)
    r = cliente.get("/precision", params={"deporte": "FUTBOL", "tipo": "RESULTADO_PARTIDO"})
    assert r.status_code == 503
    assert "conexión" not in r.text
