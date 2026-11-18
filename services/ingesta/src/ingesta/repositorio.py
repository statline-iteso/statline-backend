"""PostgreSQL access. Tables are owned by Prisma Migrate in services/api (snake_case names).

Prisma generates ids client-side, so every insert here sets `id` with uuid4. Upserts use the same
unique keys as schema.prisma, so re-running a day is idempotent.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Protocol

import psycopg

from ingesta.modelos import Deporte, EquipoNorm, EstadisticaNorm, JugadorNorm, PartidoNorm


class Repositorio(Protocol):
    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str: ...
    def iniciar_ejecucion(self, deporte: Deporte, proveedor: str) -> str: ...
    def finalizar_ejecucion(
        self,
        ejecucion_id: str,
        *,
        exitosa: bool,
        registros: int,
        peticiones: int,
        proveedor: str | None = None,
        error: str | None,
    ) -> None: ...
    def guardar_partido(self, liga_id: str, partido: PartidoNorm) -> str: ...
    def guardar_estadistica(
        self, deporte: Deporte, liga_id: str, partido_id: str, linea: EstadisticaNorm
    ) -> None: ...


class LigaNoSembradaError(LookupError):
    """The league row comes from the seed (`pnpm db:seed` in services/api)."""


class RepositorioPostgres:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    @classmethod
    def conectar(cls, database_url: str) -> "RepositorioPostgres":
        return cls(psycopg.connect(database_url, autocommit=True))

    def liga_id(self, deporte: Deporte, proveedor: str, proveedor_liga_id: str) -> str:
        fila = self._conn.execute(
            "SELECT id FROM liga WHERE deporte = %s::deporte AND proveedor = %s"
            " AND proveedor_liga_id = %s AND activa ORDER BY creado_en DESC LIMIT 1",
            (deporte.value, proveedor, proveedor_liga_id),
        ).fetchone()
        if fila is None:
            raise LigaNoSembradaError(f"no hay liga activa {proveedor}/{proveedor_liga_id}")
        return str(fila[0])

    def iniciar_ejecucion(self, deporte: Deporte, proveedor: str) -> str:
        ejecucion_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO ejecucion_ingesta (id, deporte, proveedor, estatus)"
            " VALUES (%s, %s::deporte, %s, 'EN_CURSO')",
            (ejecucion_id, deporte.value, proveedor),
        )
        return ejecucion_id

    def finalizar_ejecucion(
        self,
        ejecucion_id: str,
        *,
        exitosa: bool,
        registros: int,
        peticiones: int,
        proveedor: str | None = None,
        error: str | None,
    ) -> None:
        self._conn.execute(
            "UPDATE ejecucion_ingesta SET estatus = %s::estatus_ingesta, finalizada_en = %s,"
            " registros_procesados = %s, peticiones_usadas = %s,"
            " proveedor = COALESCE(%s, proveedor), error = %s WHERE id = %s",
            (
                "EXITOSA" if exitosa else "FALLIDA",
                datetime.now(UTC),
                registros,
                peticiones,
                proveedor,
                error,
                ejecucion_id,
            ),
        )

    def _equipo(self, liga_id: str, equipo: EquipoNorm) -> str:
        fila = self._conn.execute(
            "INSERT INTO equipo (id, liga_id, nombre, abreviatura, logo_url, proveedor_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (liga_id, proveedor_id) DO UPDATE SET nombre = EXCLUDED.nombre,"
            " logo_url = COALESCE(EXCLUDED.logo_url, equipo.logo_url) RETURNING id",
            (
                str(uuid.uuid4()),
                liga_id,
                equipo.nombre,
                equipo.abreviatura,
                equipo.logo_url,
                equipo.proveedor_id,
            ),
        ).fetchone()
        assert fila is not None
        return str(fila[0])

    def _jugador(self, deporte: Deporte, equipo_id: str, jugador: JugadorNorm) -> str:
        fila = self._conn.execute(
            "INSERT INTO jugador (id, equipo_id, deporte, nombre, posicion, proveedor_id)"
            " VALUES (%s, %s, %s::deporte, %s, %s, %s)"
            " ON CONFLICT (deporte, proveedor_id) DO UPDATE SET equipo_id = EXCLUDED.equipo_id,"
            " nombre = EXCLUDED.nombre, actualizado_en = now() RETURNING id",
            (
                str(uuid.uuid4()),
                equipo_id,
                deporte.value,
                jugador.nombre,
                jugador.posicion,
                jugador.proveedor_id,
            ),
        ).fetchone()
        assert fila is not None
        return str(fila[0])

    def guardar_partido(self, liga_id: str, partido: PartidoNorm) -> str:
        with self._conn.transaction():
            local_id = self._equipo(liga_id, partido.local)
            visita_id = self._equipo(liga_id, partido.visita)
            fila = self._conn.execute(
                "INSERT INTO partido (id, liga_id, local_id, visita_id, fecha, jornada, temporada,"
                " estatus, marcador_local, marcador_visita, proveedor_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::estatus_partido, %s, %s, %s)"
                " ON CONFLICT (liga_id, proveedor_id) DO UPDATE SET fecha = EXCLUDED.fecha,"
                " estatus = EXCLUDED.estatus, marcador_local = EXCLUDED.marcador_local,"
                " marcador_visita = EXCLUDED.marcador_visita RETURNING id",
                (
                    str(uuid.uuid4()),
                    liga_id,
                    local_id,
                    visita_id,
                    partido.fecha,
                    partido.jornada,
                    partido.temporada,
                    partido.estatus.value,
                    partido.marcador_local,
                    partido.marcador_visita,
                    partido.proveedor_id,
                ),
            ).fetchone()
        assert fila is not None
        return str(fila[0])

    def guardar_estadistica(
        self, deporte: Deporte, liga_id: str, partido_id: str, linea: EstadisticaNorm
    ) -> None:
        with self._conn.transaction():
            equipo_id = self._equipo(
                liga_id, EquipoNorm(linea.equipo_proveedor_id, linea.equipo_proveedor_id)
            )
            jugador_id = self._jugador(deporte, equipo_id, linea.jugador)
            self._conn.execute(
                "INSERT INTO estadistica_jugador_partido"
                " (id, partido_id, jugador_id, equipo_id, deporte, minutos, metricas)"
                " VALUES (%s, %s, %s, %s, %s::deporte, %s, %s::jsonb)"
                " ON CONFLICT (partido_id, jugador_id) DO UPDATE SET minutos = EXCLUDED.minutos,"
                " metricas = EXCLUDED.metricas",
                (
                    str(uuid.uuid4()),
                    partido_id,
                    jugador_id,
                    equipo_id,
                    deporte.value,
                    linea.minutos,
                    json.dumps(linea.metricas),
                ),
            )
