"""Use cases behind the HTTP endpoints (SL-37, SL-38).

The transforms (`pronosticos_para`, `proyecciones_para`, `precision_*`) are pure: they take
DataFrames or dicts and need no database. The `generar_*`, `precision`, `reentrenar` and
`activar` functions do the I/O through `datos` and `registro`.

Responses are camelCase (CONVENTIONS §3, so the Node proxy passes them through); request bodies
stay snake_case (schemas.py). D-20 and D-21 describe the rules.
"""

import math
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from predicciones import datos, registro
from predicciones.datos import aplanar_metricas
from predicciones.deportes import CLASES_RESULTADO, OBJETIVOS_JUGADOR, clase_resultado
from predicciones.errores import ModeloNoEncontradoError
from predicciones.features import features_jugadores, features_partidos
from predicciones.modelos.jugador import BundleJugador, predecir_jugador
from predicciones.modelos.resultado import BundleResultado, predecir_resultado
from predicciones.schemas import (
    Deporte,
    GenerarPronosticosRequest,
    GenerarProyeccionesRequest,
    ReentrenarRequest,
    TipoInferencia,
)

Conexion = psycopg.Connection[Any]
PROB_MIN = 1e-15  # log-loss clip for a probability of exactly 0


def seleccionar_programados(
    programados: pd.DataFrame, partido_ids: Sequence[str], jornada: int | None
) -> pd.DataFrame:
    """Scheduled games filtered by ids (case-insensitive) and jornada. Empty filter = all."""
    seleccion = programados
    if partido_ids:
        seleccion = seleccion[seleccion["partido_id"].isin({p.lower() for p in partido_ids})]
    if jornada is not None:
        seleccion = seleccion[seleccion["jornada"] == jornada]
    return seleccion


def pronosticos_para(
    bundle: BundleResultado,
    historial: pd.DataFrame,
    programados: pd.DataFrame,
    *,
    partido_ids: Sequence[str] = (),
    jornada: int | None = None,
) -> list[dict[str, Any]]:
    """Outcome forecasts for the selected scheduled games.

    Team features come from the finished games (`historial`) plus the scheduled ones. A scheduled
    game has no score, so it never enters the history; its features only use games strictly
    before its date.
    """
    objetivo = seleccionar_programados(programados, partido_ids, jornada)
    if objetivo.empty:
        return []
    combinado = pd.concat([historial, programados], ignore_index=True)
    features = features_partidos(combinado, ventana=bundle.ventana)
    salida = predecir_resultado(bundle, features.loc[objetivo["partido_id"].tolist()])
    filas: list[dict[str, Any]] = []
    for partido_id, fila in salida.iterrows():
        filas.append(
            {
                "id": str(uuid.uuid4()),
                "partido_id": str(partido_id),
                "prob_local": float(fila["prob_local"]),
                "prob_empate": float(fila["prob_empate"]),
                "prob_visita": float(fila["prob_visita"]),
                "marcador_esperado_local": float(fila["marcador_esperado_local"]),
                "marcador_esperado_visita": float(fila["marcador_esperado_visita"]),
            }
        )
    return filas


def proyecciones_para(
    bundle: BundleJugador,
    historial: pd.DataFrame,
    programados: pd.DataFrame,
    jugadores: pd.DataFrame,
    *,
    jugador_ids: Sequence[str] = (),
    jornada: int | None = None,
) -> list[dict[str, Any]]:
    """Projections for each player's next scheduled game (the earliest one on his team).

    A player with no scheduled game in the selection gets no row.
    """
    partidos = seleccionar_programados(programados, (), jornada)
    if partidos.empty or jugadores.empty:
        return []
    if jugador_ids:
        jugadores = jugadores[jugadores["jugador_id"].isin({j.lower() for j in jugador_ids})]
    por_equipo = pd.concat(
        [
            partidos.assign(equipo_id=partidos["local_id"]),
            partidos.assign(equipo_id=partidos["visita_id"]),
        ],
        ignore_index=True,
    )[["partido_id", "fecha", "local_id", "visita_id", "equipo_id"]]
    proximos = (
        jugadores.merge(por_equipo, on="equipo_id")
        .sort_values(["fecha", "partido_id"])
        .drop_duplicates("jugador_id", keep="first")
        .reset_index(drop=True)
    )
    if proximos.empty:
        return []
    consultas = proximos[["jugador_id", "equipo_id", "local_id", "visita_id", "fecha"]]
    features = features_jugadores(historial, consultas, bundle.objetivos, ventana=bundle.ventana)
    salida = predecir_jugador(bundle, features)
    valores = salida.loc[:, list(bundle.objetivos)].round(2)
    filas: list[dict[str, Any]] = []
    for indice, fila in proximos.iterrows():
        filas.append(
            {
                "id": str(uuid.uuid4()),
                "jugador_id": str(fila["jugador_id"]),
                "partido_id": str(fila["partido_id"]),
                "metricas": {o: float(valores.at[indice, o]) for o in bundle.objetivos},  # type: ignore[arg-type]
            }
        )
    return filas


def precision_resultado(deporte: Deporte, filas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Accuracy (argmax over the classes) and log-loss. Tied NBA/NFL games are not counted."""
    clases = CLASES_RESULTADO[deporte]
    n = 0
    aciertos = 0
    perdida = 0.0
    for fila in filas:
        real = clase_resultado(
            deporte, float(fila["marcador_local"]), float(fila["marcador_visita"])
        )
        if real is None:
            continue
        probs = {
            "L": float(fila["prob_local"]),
            "E": float(fila["prob_empate"]),
            "V": float(fila["prob_visita"]),
        }
        n += 1
        prediccion = max(clases, key=probs.__getitem__)
        aciertos += int(prediccion == real)
        perdida += -math.log(min(max(probs[real], PROB_MIN), 1.0))
    return {
        "n": n,
        "aciertos": aciertos,
        "accuracy": aciertos / n if n else None,
        "logLoss": perdida / n if n else None,
    }


def precision_proyeccion(deporte: Deporte, filas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """MAE per target over (projection, actual stat line) pairs. `n` counts the pairs."""
    objetivos = OBJETIVOS_JUGADOR[deporte]
    errores: dict[str, list[float]] = {o: [] for o in objetivos}
    for fila in filas:
        proyectado = fila["proyeccion"]
        real = aplanar_metricas(fila["estadistica"])
        for objetivo in objetivos:
            if objetivo in proyectado and objetivo in real:
                errores[objetivo].append(abs(float(proyectado[objetivo]) - real[objetivo]))
    return {
        "n": len(filas),
        "porObjetivo": {
            o: {"n": len(e), "mae": sum(e) / len(e) if e else None} for o, e in errores.items()
        },
    }


def _modelo_json(info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": info["id"],
        "version": info["version"],
        "nombreMetrica": info["nombre_metrica"],
        "metricaError": info["metrica_error"],
    }


def generar_pronosticos(
    conn: Conexion, body: GenerarPronosticosRequest, cache_dir: Path
) -> dict[str, Any]:
    modelo = registro.cargar_activo(conn, body.deporte, TipoInferencia.RESULTADO_PARTIDO, cache_dir)
    historial = datos.cargar_partidos(conn, body.deporte)
    programados = datos.cargar_partidos_programados(conn, body.deporte)
    filas = pronosticos_para(
        modelo.bundle,
        historial,
        programados,
        partido_ids=body.partido_ids,
        jornada=body.jornada,
    )
    datos.reemplazar_pronosticos(conn, modelo.modelo_id, filas)
    return {
        "deporte": body.deporte.value,
        "modeloId": modelo.modelo_id,
        "generados": len(filas),
        "pronosticos": [
            {
                "id": f["id"],
                "partidoId": f["partido_id"],
                "probLocal": f["prob_local"],
                "probEmpate": f["prob_empate"],
                "probVisita": f["prob_visita"],
                "marcadorEsperadoLocal": f["marcador_esperado_local"],
                "marcadorEsperadoVisita": f["marcador_esperado_visita"],
            }
            for f in filas
        ],
    }


def generar_proyecciones(
    conn: Conexion, body: GenerarProyeccionesRequest, cache_dir: Path
) -> dict[str, Any]:
    modelo = registro.cargar_activo(
        conn, body.deporte, TipoInferencia.PROYECCION_JUGADOR, cache_dir
    )
    historial = datos.cargar_lineas(conn, body.deporte)
    programados = datos.cargar_partidos_programados(conn, body.deporte)
    jugadores = datos.cargar_jugadores(conn, body.deporte)
    filas = proyecciones_para(
        modelo.bundle,
        historial,
        programados,
        jugadores,
        jugador_ids=body.jugador_ids,
        jornada=body.jornada,
    )
    datos.reemplazar_proyecciones(conn, modelo.modelo_id, filas)
    return {
        "deporte": body.deporte.value,
        "modeloId": modelo.modelo_id,
        "generados": len(filas),
        "proyecciones": [
            {
                "id": f["id"],
                "jugadorId": f["jugador_id"],
                "partidoId": f["partido_id"],
                "metricas": f["metricas"],
            }
            for f in filas
        ],
    }


def precision(conn: Conexion, deporte: Deporte, tipo: TipoInferencia) -> dict[str, Any]:
    """Precision of the active model's stored rows against the finished games."""
    info = datos.cargar_info_modelo_activo(conn, deporte, tipo)
    if tipo is TipoInferencia.RESULTADO_PARTIDO:
        cuerpo = precision_resultado(deporte, datos.cargar_pronosticos_resueltos(conn, info["id"]))
    else:
        cuerpo = precision_proyeccion(
            deporte, datos.cargar_proyecciones_resueltas(conn, info["id"])
        )
    return {
        "deporte": deporte.value,
        "tipo": tipo.value,
        "modelo": _modelo_json(info),
        "precision": cuerpo,
    }


def reentrenar(conn: Conexion, body: ReentrenarRequest) -> dict[str, Any]:
    r = registro.entrenar_y_registrar(conn, body.deporte, body.tipo)
    return {
        "modeloId": r["modelo_id"],
        "version": r["version"],
        "deporte": r["deporte"],
        "tipo": r["tipo"],
        "nombreMetrica": r["nombre_metrica"],
        "metrica": r["metrica"],
        "baseline": r["baseline"],
        "nTrain": r["n_train"],
        "nTest": r["n_test"],
        "activado": r["activado"],
        "motivo": r["motivo"],
    }


def activar(conn: Conexion, modelo_id: str) -> dict[str, Any]:
    """Admin override: makes the model active WITHOUT the D-18 baseline check."""
    try:
        normalizado = str(uuid.UUID(modelo_id))
    except ValueError as err:
        raise ModeloNoEncontradoError(modelo_id) from err
    registro.activar(conn, normalizado)
    return {"modeloId": normalizado, "activo": True}
