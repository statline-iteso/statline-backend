"""Model registry (SL-36): versions in `modelo_prediccion`, bytes in `modelo_artefacto` (D-28).

Activation rule (D-31): a candidate is activated only when its metric beats its baseline, and,
when a model is already active for (deporte, tipo), when it is no worse than that model on the
same metric. Activation is one transaction that deactivates the other versions of the group.

Artifacts are pickles (joblib). Only load bytes from the database this service writes.
"""

import hashlib
import io
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import psycopg

from predicciones.config import Settings
from predicciones.datos import cargar_lineas, cargar_partidos
from predicciones.deportes import VENTANA_DEFAULT
from predicciones.errores import (
    ArtefactoInvalidoError,
    ModeloNoEncontradoError,
    SinModeloActivoError,
)
from predicciones.modelos.base import ResultadoEntrenamiento
from predicciones.modelos.jugador import entrenar_jugador
from predicciones.modelos.resultado import entrenar_resultado
from predicciones.schemas import Deporte, TipoInferencia

PREFIJO_DB = "db://"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class RegistroModelo:
    modelo_id: str
    artefacto_id: str
    version: str
    sha256: str


@dataclass(frozen=True)
class ModeloCargado:
    modelo_id: str
    version: str
    sha256: str
    bundle: Any


def serializar(bundle: Any) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(bundle, buffer)
    return buffer.getvalue()


def deserializar(datos: bytes) -> Any:
    return joblib.load(io.BytesIO(datos))


def sha256_hex(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def version_para(ahora: datetime, *, sintetico: bool) -> str:
    """`YYYYMMDDHHMMSS`, with `-synthetic` when the training data comes from the demo seeder."""
    return ahora.strftime("%Y%m%d%H%M%S") + ("-synthetic" if sintetico else "")


def registrar(
    conn: psycopg.Connection[Any],
    resultado: ResultadoEntrenamiento,
    *,
    sintetico: bool,
    ahora: datetime | None = None,
) -> RegistroModelo:
    """Insert a new inactive version and its artifact in one transaction."""
    momento = ahora or datetime.now(UTC)
    datos = serializar(resultado.bundle)
    digest = sha256_hex(datos)
    modelo_id = str(uuid.uuid4())
    artefacto_id = str(uuid.uuid4())
    version = version_para(momento, sintetico=sintetico)
    with conn.transaction():
        conn.execute(
            "INSERT INTO modelo_prediccion (id, deporte, tipo, version, artefacto_uri,"
            " nombre_metrica, metrica_error, activo, entrenado_en)"
            " VALUES (%s::uuid, %s::deporte, %s::tipo_inferencia, %s, %s, %s, %s, false, %s)",
            (
                modelo_id,
                resultado.deporte.value,
                resultado.tipo.value,
                version,
                f"{PREFIJO_DB}{artefacto_id}",
                resultado.nombre_metrica,
                resultado.metrica,
                momento,
            ),
        )
        conn.execute(
            "INSERT INTO modelo_artefacto (id, modelo_id, contenido, sha256, tamano_bytes,"
            " creado_en) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)",
            (artefacto_id, modelo_id, datos, digest, len(datos), momento),
        )
    return RegistroModelo(modelo_id, artefacto_id, version, digest)


def activar(conn: psycopg.Connection[Any], modelo_id: str) -> None:
    """Make `modelo_id` the only active version of its (deporte, tipo), atomically."""
    with conn.transaction():
        fila = conn.execute(
            "SELECT deporte::text, tipo::text FROM modelo_prediccion WHERE id = %s::uuid",
            (modelo_id,),
        ).fetchone()
        if fila is None:
            raise ModeloNoEncontradoError(modelo_id)
        deporte, tipo = str(fila[0]), str(fila[1])
        # Lock the whole group so two activations cannot interleave.
        conn.execute(
            "SELECT id FROM modelo_prediccion WHERE deporte = %s::deporte"
            " AND tipo = %s::tipo_inferencia ORDER BY id FOR UPDATE",
            (deporte, tipo),
        )
        conn.execute(
            "UPDATE modelo_prediccion SET activo = (id = %s::uuid)"
            " WHERE deporte = %s::deporte AND tipo = %s::tipo_inferencia"
            " AND activo <> (id = %s::uuid)",
            (modelo_id, deporte, tipo, modelo_id),
        )


def decidir_activacion(
    supera_baseline: bool, metrica: float, metrica_activa: float | None
) -> tuple[bool, str]:
    """Activation rule of D-31. Returns (activate, reason)."""
    if not supera_baseline:
        return False, "no supera el baseline"
    if metrica_activa is None:
        return True, "primer modelo que supera el baseline"
    if metrica <= metrica_activa:
        return True, "supera el baseline y no empeora al activo"
    return False, "supera el baseline pero empeora al modelo activo"


def _metrica_activa(
    conn: psycopg.Connection[Any], deporte: Deporte, tipo: TipoInferencia
) -> float | None:
    fila = conn.execute(
        "SELECT metrica_error FROM modelo_prediccion WHERE deporte = %s::deporte"
        " AND tipo = %s::tipo_inferencia AND activo",
        (deporte.value, tipo.value),
    ).fetchone()
    return None if fila is None else float(fila[0])


def entrenar_y_registrar(
    conn: psycopg.Connection[Any],
    deporte: Deporte,
    tipo: TipoInferencia,
    *,
    ventana: int = VENTANA_DEFAULT,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Train on the database, register the version and activate it when D-31 allows."""
    if tipo is TipoInferencia.RESULTADO_PARTIDO:
        partidos = cargar_partidos(conn, deporte)
        resultado = entrenar_resultado(deporte, partidos, ventana=ventana)
        sintetico = bool(partidos["es_demo"].any())
    else:
        lineas = cargar_lineas(conn, deporte)
        resultado = entrenar_jugador(deporte, lineas, ventana=ventana)
        sintetico = bool(lineas["es_demo"].any())
    registro = registrar(conn, resultado, sintetico=sintetico, ahora=ahora)
    activa = _metrica_activa(conn, deporte, tipo)
    activar_ok, motivo = decidir_activacion(resultado.supera_baseline, resultado.metrica, activa)
    if activar_ok:
        activar(conn, registro.modelo_id)
    return {
        "modelo_id": registro.modelo_id,
        "version": registro.version,
        "deporte": deporte.value,
        "tipo": tipo.value,
        "nombre_metrica": resultado.nombre_metrica,
        "metrica": resultado.metrica,
        "baseline": resultado.baseline,
        "n_train": resultado.n_train,
        "n_test": resultado.n_test,
        "activado": activar_ok,
        "motivo": motivo,
    }


def _leer_cache(ruta: Path, sha: str) -> bytes | None:
    if not ruta.is_file():
        return None
    datos = ruta.read_bytes()
    if sha256_hex(datos) == sha:
        return datos
    ruta.unlink(missing_ok=True)  # corrupt or tampered cache entry: refetch from the database
    return None


def _escribir_cache(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporal = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as archivo:
        archivo.write(datos)
    os.replace(temporal, ruta)


def _contenido_desde_db(conn: psycopg.Connection[Any], uri: str) -> bytes:
    if not uri.startswith(PREFIJO_DB):
        raise ArtefactoInvalidoError(f"artefacto_uri no soportado: {uri[:20]}")
    try:
        artefacto_id = str(uuid.UUID(uri.removeprefix(PREFIJO_DB)))
    except ValueError as err:
        raise ArtefactoInvalidoError("artefacto_uri con id inválido") from err
    fila = conn.execute(
        "SELECT contenido FROM modelo_artefacto WHERE id = %s::uuid", (artefacto_id,)
    ).fetchone()
    if fila is None:
        raise ArtefactoInvalidoError("el artefacto no existe")
    return bytes(fila[0])


def cargar_activo(
    conn: psycopg.Connection[Any],
    deporte: Deporte,
    tipo: TipoInferencia,
    cache_dir: Path | None = None,
) -> ModeloCargado:
    """Load the active model. Bytes are cached under `cache_dir/<sha256>.joblib` and verified.

    `cache_dir` defaults to the `ARTEFACTOS_DIR` setting (`/tmp/statline-modelos`).
    """
    cache_dir = cache_dir or Path(Settings().artefactos_dir)
    fila = conn.execute(
        "SELECT m.id::text, m.version, m.artefacto_uri, a.sha256 FROM modelo_prediccion m"
        " LEFT JOIN modelo_artefacto a ON a.modelo_id = m.id"
        " WHERE m.deporte = %s::deporte AND m.tipo = %s::tipo_inferencia AND m.activo",
        (deporte.value, tipo.value),
    ).fetchone()
    if fila is None:
        raise SinModeloActivoError(f"no hay modelo activo para {deporte.value}/{tipo.value}")
    modelo_id, version, uri, sha = str(fila[0]), str(fila[1]), str(fila[2]), fila[3]
    if sha is None or not _SHA256.fullmatch(str(sha)):
        raise ArtefactoInvalidoError("el modelo activo no tiene un sha256 válido")
    sha = str(sha)
    ruta = cache_dir / f"{sha}.joblib"
    datos = _leer_cache(ruta, sha)
    if datos is None:
        datos = _contenido_desde_db(conn, uri)
        if sha256_hex(datos) != sha:
            raise ArtefactoInvalidoError("el artefacto no coincide con su sha256")
        _escribir_cache(ruta, datos)
    return ModeloCargado(modelo_id, version, sha, deserializar(datos))
