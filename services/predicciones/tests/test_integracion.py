"""Runs the real SQL against PostgreSQL with the Prisma migrations applied.

Skipped unless DATABASE_URL is set. Each test seeds synthetic games inside one transaction and
rolls it back, so the database is left as it was. CI runs `pytest -m integration`.
"""

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from fabrica import generar_datos

from predicciones.datos import cargar_lineas, cargar_partidos, cargar_partidos_programados
from predicciones.registro import cargar_activo, entrenar_y_registrar
from predicciones.schemas import Deporte, TipoInferencia

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"),
]

LIGA_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "liga-test"))


def _id(texto: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, texto))


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[object]]:
    conexion = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        yield conexion
    finally:
        conexion.rollback()
        conexion.close()


def _sembrar(conn: psycopg.Connection[object], deporte: Deporte, partidos: int) -> None:
    datos_p, datos_l = generar_datos(deporte, partidos=partidos, seed=31)
    conn.execute(
        "INSERT INTO liga (id, nombre, deporte, temporada, proveedor, proveedor_liga_id)"
        " VALUES (%s, 'Prueba', %s::deporte, '2025-2026', 'demo', %s)",
        (LIGA_ID, deporte.value, _id(f"liga-{deporte.value}")),
    )
    equipos = set(datos_p["local_id"]) | set(datos_p["visita_id"])
    for equipo in equipos:
        conn.execute(
            "INSERT INTO equipo (id, liga_id, nombre, proveedor_id) VALUES (%s, %s, %s, %s)",
            (_id(equipo), LIGA_ID, equipo, equipo),
        )
    for fila in datos_p.itertuples(index=False):
        conn.execute(
            "INSERT INTO partido (id, liga_id, local_id, visita_id, fecha, jornada, temporada,"
            " estatus, marcador_local, marcador_visita, proveedor_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, '2025-2026', 'FINALIZADO', %s, %s, %s)",
            (
                _id(fila.partido_id),
                LIGA_ID,
                _id(fila.local_id),
                _id(fila.visita_id),
                fila.fecha,
                int(fila.jornada),
                int(fila.marcador_local),
                int(fila.marcador_visita),
                fila.proveedor_id,
            ),
        )
    objetivos = [c for c in datos_l.columns if c not in _NO_METRICAS]
    equipo_de = datos_l.drop_duplicates("jugador_id").set_index("jugador_id")["equipo_id"]
    for jugador in set(datos_l["jugador_id"]):
        conn.execute(
            "INSERT INTO jugador (id, deporte, nombre, proveedor_id, equipo_id)"
            " VALUES (%s, %s::deporte, %s, %s, %s)",
            (_id(jugador), deporte.value, jugador, jugador, _id(equipo_de[jugador])),
        )
    for fila in datos_l.to_dict("records"):
        metricas = _anidar({o: int(fila[o]) for o in objetivos if fila[o] == fila[o]})
        conn.execute(
            "INSERT INTO estadistica_jugador_partido (id, partido_id, jugador_id, equipo_id,"
            " deporte, minutos, metricas) VALUES (%s, %s, %s, %s, %s::deporte, %s, %s::jsonb)",
            (
                str(uuid.uuid4()),
                _id(fila["partido_id"]),
                _id(fila["jugador_id"]),
                _id(fila["equipo_id"]),
                deporte.value,
                int(fila["minutos"]),
                json.dumps(metricas),
            ),
        )


def _anidar(planas: dict[str, int]) -> dict[str, object]:
    """Turn dotted keys back into nested groups, as the NFL schema stores them."""
    anidado: dict[str, object] = {}
    for clave, valor in planas.items():
        grupo, _, campo = clave.partition(".")
        if campo:
            subgrupo = anidado.setdefault(grupo, {})
            assert isinstance(subgrupo, dict)
            subgrupo[campo] = valor
        else:
            anidado[clave] = valor
    return anidado


_NO_METRICAS = {
    "partido_id", "jugador_id", "equipo_id", "fecha", "local_id", "visita_id", "minutos", "es_demo",
}  # fmt: skip


def test_cargar_partidos_y_lineas_con_postgres(conn: psycopg.Connection[object]) -> None:
    _sembrar(conn, Deporte.BASQUETBOL, partidos=40)
    partidos = cargar_partidos(conn, Deporte.BASQUETBOL)  # type: ignore[arg-type]
    assert len(partidos) == 40
    assert partidos["es_demo"].all()
    assert partidos["fecha"].dt.tz is not None
    lineas = cargar_lineas(conn, Deporte.BASQUETBOL)  # type: ignore[arg-type]
    assert {"puntos", "rebotes", "asistencias", "minutos"} <= set(lineas.columns)
    assert lineas["puntos"].notna().all()
    assert cargar_partidos_programados(conn, Deporte.BASQUETBOL).empty  # type: ignore[arg-type]


def test_entrenar_registrar_y_cargar_activo(
    conn: psycopg.Connection[object], tmp_path: Path
) -> None:
    _sembrar(conn, Deporte.BASQUETBOL, partidos=160)
    resumen = entrenar_y_registrar(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        ahora=datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC),
    )
    assert resumen["activado"] is True
    assert resumen["version"].endswith("-synthetic")
    activo = cargar_activo(
        conn,  # type: ignore[arg-type]
        Deporte.BASQUETBOL,
        TipoInferencia.RESULTADO_PARTIDO,
        tmp_path,
    )
    assert activo.modelo_id == resumen["modelo_id"]
    assert set(activo.bundle.clases) == {"L", "V"}


def test_nfl_guarda_grupos_anidados_y_se_aplanan(conn: psycopg.Connection[object]) -> None:
    _sembrar(conn, Deporte.AMERICANO, partidos=30)
    lineas = cargar_lineas(conn, Deporte.AMERICANO)  # type: ignore[arg-type]
    assert {"pase.yardas", "carrera.yardas", "recepcion.yardas"} <= set(lineas.columns)
    assert lineas["pase.yardas"].notna().any()
    assert lineas["pase.yardas"].isna().any()


def _programar(conn: psycopg.Connection[object], n: int) -> list[str]:
    """Insert n scheduled games between the seeded teams; returns their ids."""
    equipos = [
        fila[0]
        for fila in conn.execute(
            "SELECT id::text FROM equipo WHERE liga_id = %s ORDER BY nombre", (LIGA_ID,)
        ).fetchall()
    ]
    ids = []
    for i in range(n):
        pid = _id(f"programado-{i}")
        conn.execute(
            "INSERT INTO partido (id, liga_id, local_id, visita_id, fecha, jornada, temporada,"
            " estatus, proveedor_id) VALUES (%s, %s, %s, %s, %s, 99, '2025-2026', 'PROGRAMADO',"
            " %s)",
            (
                pid,
                LIGA_ID,
                equipos[i % len(equipos)],
                equipos[(i + 1) % len(equipos)],
                datetime(2026, 3, 1 + i, 20, tzinfo=UTC),
                f"demo-programado-{i}",
            ),
        )
        ids.append(pid)
    return ids


def test_http_reentrena_genera_y_mide_precision(
    conn: psycopg.Connection[object], tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from predicciones.config import Settings
    from predicciones.main import create_app, get_conn, get_settings

    _sembrar(conn, Deporte.BASQUETBOL, partidos=160)
    _programar(conn, 4)
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused", artefactos_dir=str(tmp_path)
    )
    cliente = TestClient(app)

    entreno = cliente.post(
        "/modelos/reentrenar", json={"deporte": "BASQUETBOL", "tipo": "RESULTADO_PARTIDO"}
    )
    assert entreno.status_code == 200, entreno.text
    assert entreno.json()["activado"] is True

    primera = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL", "jornada": 99})
    assert primera.status_code == 200, primera.text
    assert primera.json()["generados"] == 4
    segunda = cliente.post("/pronosticos/generar", json={"deporte": "BASQUETBOL", "jornada": 99})
    assert segunda.json()["generados"] == 4
    filas = conn.execute(
        "SELECT count(*) FROM pronostico_partido WHERE modelo_id = %s::uuid",
        (primera.json()["modeloId"],),
    ).fetchone()
    assert filas is not None and filas[0] == 4  # re-running replaces, it does not duplicate

    # Finish the scheduled games (home team wins) and measure the stored forecasts.
    conn.execute(
        "UPDATE partido SET estatus = 'FINALIZADO', marcador_local = 100, marcador_visita = 90"
        " WHERE jornada = 99"
    )
    precision = cliente.get(
        "/precision", params={"deporte": "BASQUETBOL", "tipo": "RESULTADO_PARTIDO"}
    )
    assert precision.status_code == 200, precision.text
    cuerpo = precision.json()
    assert cuerpo["precision"]["n"] == 4
    assert 0.0 <= cuerpo["precision"]["accuracy"] <= 1.0
    assert cuerpo["precision"]["logLoss"] is not None
    assert cuerpo["modelo"]["version"].endswith("-synthetic")


def test_http_proyecciones_y_precision_de_jugadores(
    conn: psycopg.Connection[object], tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from predicciones.config import Settings
    from predicciones.main import create_app, get_conn, get_settings

    _sembrar(conn, Deporte.BASQUETBOL, partidos=160)
    _programar(conn, 2)
    app = create_app()
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused", artefactos_dir=str(tmp_path)
    )
    cliente = TestClient(app)

    entreno = cliente.post(
        "/modelos/reentrenar", json={"deporte": "BASQUETBOL", "tipo": "PROYECCION_JUGADOR"}
    )
    assert entreno.status_code == 200, entreno.text
    generado = cliente.post("/proyecciones/generar", json={"deporte": "BASQUETBOL", "jornada": 99})
    assert generado.status_code == 200, generado.text
    proyecciones = generado.json()["proyecciones"]
    assert proyecciones

    # Store an actual stat line for each projected player in his game, then measure.
    for proy in proyecciones:
        equipo = conn.execute(
            "SELECT equipo_id FROM jugador WHERE id = %s", (proy["jugadorId"],)
        ).fetchone()
        assert equipo is not None
        conn.execute(
            "UPDATE partido SET estatus = 'FINALIZADO', marcador_local = 100,"
            " marcador_visita = 90 WHERE id = %s AND estatus <> 'FINALIZADO'",
            (proy["partidoId"],),
        )
        conn.execute(
            "INSERT INTO estadistica_jugador_partido (id, partido_id, jugador_id, equipo_id,"
            " deporte, minutos, metricas) VALUES (%s, %s, %s, %s, 'BASQUETBOL', 30, %s::jsonb)",
            (
                str(uuid.uuid4()),
                proy["partidoId"],
                proy["jugadorId"],
                equipo[0],
                json.dumps({"puntos": 12, "rebotes": 5, "asistencias": 3}),
            ),
        )
    precision = cliente.get(
        "/precision", params={"deporte": "BASQUETBOL", "tipo": "PROYECCION_JUGADOR"}
    )
    assert precision.status_code == 200, precision.text
    cuerpo = precision.json()["precision"]
    assert cuerpo["n"] == len(proyecciones)
    assert cuerpo["porObjetivo"]["puntos"]["n"] == len(proyecciones)
    assert cuerpo["porObjetivo"]["puntos"]["mae"] is not None
