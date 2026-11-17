import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fabrica import generar_datos

from predicciones import registro
from predicciones.errores import (
    ArtefactoInvalidoError,
    ModeloNoEncontradoError,
    SinModeloActivoError,
)
from predicciones.features import features_partidos
from predicciones.modelos.base import ResultadoEntrenamiento
from predicciones.modelos.resultado import entrenar_resultado, predecir_resultado
from predicciones.registro import (
    activar,
    cargar_activo,
    decidir_activacion,
    deserializar,
    entrenar_y_registrar,
    registrar,
    serializar,
    sha256_hex,
    version_para,
)
from predicciones.schemas import Deporte, TipoInferencia

AHORA = datetime(2026, 11, 16, 12, 30, 5, tzinfo=UTC)
UUID_ARTEFACTO = "aaaaaaaa-0000-0000-0000-000000000000"


class _Resultado:
    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._filas[0] if self._filas else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._filas


class FakeConn:
    """Records every statement. A SELECT gets the rows of the first scripted key found in it."""

    def __init__(self, respuestas: dict[str, list[tuple[Any, ...]]] | None = None) -> None:
        self.sentencias: list[tuple[str, Any]] = []
        self.respuestas = respuestas or {}

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.sentencias.append(("BEGIN", None))
        yield
        self.sentencias.append(("COMMIT", None))

    def execute(self, sql: str, params: Any = None) -> _Resultado:
        sql = " ".join(sql.split())
        self.sentencias.append((sql, params))
        for clave, filas in self.respuestas.items():
            if clave in sql:
                return _Resultado(filas)
        return _Resultado([])

    def sql_de(self, fragmento: str) -> list[tuple[str, Any]]:
        return [s for s in self.sentencias if fragmento in s[0]]

    def tipos(self) -> list[str]:
        return [s[0] for s in self.sentencias]


def _resultado_basquetbol() -> ResultadoEntrenamiento:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=120, seed=8)
    return entrenar_resultado(Deporte.BASQUETBOL, partidos)


@pytest.fixture(scope="module")
def resultado() -> ResultadoEntrenamiento:
    return _resultado_basquetbol()


def _conn_con_artefacto(datos: bytes) -> FakeConn:
    uri = f"db://{UUID_ARTEFACTO}"
    return FakeConn(
        {
            "FROM modelo_prediccion m": [("m-1", "20261116123005", uri, sha256_hex(datos))],
            "SELECT contenido": [(datos,)],
        }
    )


def test_serializacion_ida_y_vuelta_conserva_el_modelo(resultado: ResultadoEntrenamiento) -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=120, seed=8)
    feats = features_partidos(partidos).tail(3)
    original = predecir_resultado(resultado.bundle, feats)
    recuperado = predecir_resultado(deserializar(serializar(resultado.bundle)), feats)
    assert original.equals(recuperado)


def test_version_con_sufijo_sintetico() -> None:
    assert version_para(AHORA, sintetico=False) == "20261116123005"
    assert version_para(AHORA, sintetico=True) == "20261116123005-synthetic"


def test_registrar_inserta_modelo_y_artefacto_en_una_transaccion(
    resultado: ResultadoEntrenamiento,
) -> None:
    conn = FakeConn()
    reg = registrar(conn, resultado, sintetico=True, ahora=AHORA)  # type: ignore[arg-type]
    assert conn.tipos()[0] == "BEGIN"
    assert conn.tipos()[-1] == "COMMIT"
    ((sql_modelo, params_modelo),) = conn.sql_de("INSERT INTO modelo_prediccion")
    assert params_modelo[0] == reg.modelo_id
    assert params_modelo[1:4] == ("BASQUETBOL", "RESULTADO_PARTIDO", "20261116123005-synthetic")
    assert params_modelo[4] == f"db://{reg.artefacto_id}"
    assert params_modelo[5:7] == ("log_loss", resultado.metrica)
    assert " false, " in sql_modelo
    ((_, params_art),) = conn.sql_de("INSERT INTO modelo_artefacto")
    assert params_art[0] == reg.artefacto_id and params_art[1] == reg.modelo_id
    assert params_art[3] == reg.sha256 == sha256_hex(params_art[2])
    assert params_art[4] == len(params_art[2])
    assert conn.tipos().index(sql_modelo) < conn.tipos().index(
        next(s for s, _ in conn.sentencias if "INSERT INTO modelo_artefacto" in s)
    )


def test_activar_desactiva_el_grupo_y_activa_uno() -> None:
    conn = FakeConn({"SELECT deporte::text": [("BASQUETBOL", "RESULTADO_PARTIDO")]})
    activar(conn, "m-1")  # type: ignore[arg-type]
    assert conn.tipos()[0] == "BEGIN" and conn.tipos()[-1] == "COMMIT"
    ((_, params_bloqueo),) = conn.sql_de("FOR UPDATE")
    assert params_bloqueo == ("BASQUETBOL", "RESULTADO_PARTIDO")
    ((sql, params),) = conn.sql_de("UPDATE modelo_prediccion SET activo")
    assert "SET activo = (id = %s::uuid)" in sql
    assert "WHERE deporte = %s::deporte AND tipo = %s::tipo_inferencia" in sql
    assert "activo <> (id = %s::uuid)" in sql
    assert params == ("m-1", "BASQUETBOL", "RESULTADO_PARTIDO", "m-1")


def test_activar_modelo_inexistente_falla_sin_actualizar() -> None:
    conn = FakeConn()
    with pytest.raises(ModeloNoEncontradoError):
        activar(conn, "no-existe")  # type: ignore[arg-type]
    assert not conn.sql_de("UPDATE")


def test_decidir_activacion_sigue_la_regla() -> None:
    assert decidir_activacion(False, 0.5, None) == (False, "no supera el baseline")
    assert decidir_activacion(False, 0.5, 0.7)[0] is False
    assert decidir_activacion(True, 0.4, None)[0] is True
    assert decidir_activacion(True, 0.4, 0.5)[0] is True
    assert decidir_activacion(True, 0.6, 0.5)[0] is False


def test_cargar_activo_verifica_hash_y_usa_cache(
    tmp_path: Path, resultado: ResultadoEntrenamiento
) -> None:
    datos = serializar(resultado.bundle)
    conn = _conn_con_artefacto(datos)
    cargado = cargar_activo(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        tmp_path,
    )
    assert cargado.sha256 == sha256_hex(datos)
    assert (tmp_path / f"{cargado.sha256}.joblib").read_bytes() == datos
    assert conn.sql_de("SELECT contenido")

    segunda = _conn_con_artefacto(datos)
    cargar_activo(
        segunda,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        tmp_path,
    )
    assert not segunda.sql_de("SELECT contenido")


def test_cargar_activo_rechaza_artefacto_alterado_en_db(
    tmp_path: Path, resultado: ResultadoEntrenamiento
) -> None:
    datos = serializar(resultado.bundle)
    conn = _conn_con_artefacto(datos)
    conn.respuestas["SELECT contenido"] = [(datos + b"x",)]
    with pytest.raises(ArtefactoInvalidoError):
        cargar_activo(
            conn,  # type: ignore[arg-type]
            Deporte.BASQUETBOL,
            TipoInferencia.RESULTADO_PARTIDO,
            tmp_path,
        )
    assert not list(tmp_path.iterdir())


def test_cache_alterada_se_descarta_y_se_recarga(
    tmp_path: Path, resultado: ResultadoEntrenamiento
) -> None:
    datos = serializar(resultado.bundle)
    sha = sha256_hex(datos)
    (tmp_path / f"{sha}.joblib").write_bytes(b"manipulado")
    conn = _conn_con_artefacto(datos)
    cargar_activo(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        tmp_path,
    )
    assert conn.sql_de("SELECT contenido")
    assert (tmp_path / f"{sha}.joblib").read_bytes() == datos


def test_sin_modelo_activo_levanta_error(tmp_path: Path) -> None:
    with pytest.raises(SinModeloActivoError):
        cargar_activo(
            FakeConn(),  # type: ignore[arg-type]
            Deporte.FUTBOL,
            TipoInferencia.RESULTADO_PARTIDO,
            tmp_path,
        )


def test_entrenar_y_registrar_activa_si_supera_el_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=160, seed=12)
    monkeypatch.setattr(registro, "cargar_partidos", lambda conn, deporte: partidos)
    conn = FakeConn({"SELECT deporte::text": [("BASQUETBOL", "RESULTADO_PARTIDO")]})
    resumen = entrenar_y_registrar(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        ahora=AHORA,
    )
    assert resumen["version"] == "20261116123005-synthetic"
    assert resumen["activado"] is True
    assert resumen["metrica"] < resumen["baseline"]
    assert conn.sql_de("UPDATE modelo_prediccion SET activo")


def test_entrenar_y_registrar_no_activa_si_empeora_al_activo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partidos, _ = generar_datos(Deporte.BASQUETBOL, partidos=160, seed=12)
    monkeypatch.setattr(registro, "cargar_partidos", lambda conn, deporte: partidos)
    conn = FakeConn({"SELECT metrica_error": [(0.0,)]})  # el activo es perfecto
    resumen = entrenar_y_registrar(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        ahora=AHORA,
    )
    assert resumen["activado"] is False
    assert not conn.sql_de("UPDATE modelo_prediccion SET activo")


def test_sha256_detecta_cualquier_cambio() -> None:
    assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert sha256_hex(b"abc") != sha256_hex(b"abd")
