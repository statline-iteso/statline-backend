import { Router, type RequestHandler } from "express";
import type { Prisma, PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { createCrudRouter, IdParamSchema } from "../lib/crud";
import { AppError, notFound } from "../lib/errors";
import { metricasNumericas } from "../lib/metricas";
import { promediosJugador, tendenciaJugador } from "../lib/agregados";
import { calcularForma, calcularPosiciones, type ResultadoPartido } from "../lib/standings";
import {
  CreateEquipoSchema,
  CreateJugadorSchema,
  CreateLigaSchema,
  CompararQuerySchema,
  CreatePartidoSchema,
  EquipoFilterSchema,
  JugadorFilterSchema,
  LigaFilterSchema,
  PartidoFilterSchema,
  PromediosQuerySchema,
  TendenciaQuerySchema,
  UpdateEquipoSchema,
  UpdateJugadorSchema,
  UpdateLigaSchema,
  UpdatePartidoSchema,
} from "./schemas";

interface Deps {
  prisma: PrismaClient;
  /** Guard for POST/PUT/DELETE: catalog data comes from ingestion, so only ADMIN edits it. */
  adminOnly: RequestHandler;
  /** Directory with <deporte>.schema.json, relative to the repo root (SCHEMAS_DIR). */
  schemasDir?: string;
}

const finalizados = (where: Prisma.PartidoWhereInput): Prisma.PartidoWhereInput => ({
  ...where,
  estatus: "FINALIZADO",
  marcadorLocal: { not: null },
  marcadorVisita: { not: null },
});

const toResultado = (p: {
  localId: string;
  visitaId: string;
  marcadorLocal: number | null;
  marcadorVisita: number | null;
}): ResultadoPartido => ({
  localId: p.localId,
  visitaId: p.visitaId,
  marcadorLocal: p.marcadorLocal ?? 0,
  marcadorVisita: p.marcadorVisita ?? 0,
});

/** /api/ligas · filter ?deporte= · GET /:id/posiciones · GET /:id/calendario */
export function ligasRouter({ prisma, adminOnly }: Deps): Router {
  const router = Router();

  router.get(
    "/:id/posiciones",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const liga = await prisma.liga.findUnique({
        where: { id },
        include: { equipos: { select: { id: true, nombre: true, abreviatura: true } } },
      });
      if (!liga) throw notFound("Liga");
      const partidos = await prisma.partido.findMany({ where: finalizados({ ligaId: id }) });
      const tabla = calcularPosiciones(
        liga.deporte,
        liga.equipos.map((e) => e.id),
        partidos.map(toResultado),
      );
      const equipos = new Map(liga.equipos.map((e) => [e.id, e]));
      res.json({
        ligaId: id,
        deporte: liga.deporte,
        temporada: liga.temporada,
        posiciones: tabla.map((fila, i) => ({
          posicion: i + 1,
          equipo: equipos.get(fila.equipoId),
          ...fila,
        })),
      });
    }),
  );

  router.get(
    "/:id/calendario",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const partidos = await prisma.partido.findMany({
        where: { ligaId: id },
        orderBy: { fecha: "asc" },
        include: {
          local: { select: { id: true, nombre: true, abreviatura: true } },
          visita: { select: { id: true, nombre: true, abreviatura: true } },
        },
      });
      res.json({ ligaId: id, partidos });
    }),
  );

  router.use(
    createCrudRouter({
      name: "Liga",
      delegate: prisma.liga,
      createSchema: CreateLigaSchema,
      updateSchema: UpdateLigaSchema,
      filterSchema: LigaFilterSchema,
      where: (f) => (f.deporte ? { deporte: f.deporte } : {}),
      orderBy: { nombre: "asc" },
      writeGuard: adminOnly,
    }),
  );
  return router;
}

/** /api/equipos · GET /:id/forma */
export function equiposRouter({ prisma, adminOnly }: Deps): Router {
  const router = Router();

  router.get(
    "/:id/forma",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const equipo = await prisma.equipo.findUnique({ where: { id } });
      if (!equipo) throw notFound("Equipo");
      const partidos = await prisma.partido.findMany({
        where: finalizados({ OR: [{ localId: id }, { visitaId: id }] }),
        orderBy: { fecha: "desc" },
        take: 5,
      });
      res.json({
        equipoId: id,
        forma: calcularForma(id, partidos.map(toResultado)),
        partidos: partidos.map((p) => p.id),
      });
    }),
  );

  router.use(
    createCrudRouter({
      name: "Equipo",
      delegate: prisma.equipo,
      createSchema: CreateEquipoSchema,
      updateSchema: UpdateEquipoSchema,
      filterSchema: EquipoFilterSchema,
      where: () => ({}),
      orderBy: { nombre: "asc" },
      writeGuard: adminOnly,
    }),
  );
  return router;
}

const REF_JUGADOR = { id: true, nombre: true, deporte: true, posicion: true } as const;

/**
 * /api/jugadores · filters ?q= and ?deporte= · GET /:id/promedios?ultimos= ·
 * GET /:id/tendencia?metrica=&n= · GET /comparar?ids=a,b[,c,d].
 * The aggregate routes are registered above router.use so they win over /:id.
 */
export function jugadoresRouter({ prisma, adminOnly, schemasDir }: Deps): Router {
  const router = Router();

  router.get(
    "/comparar",
    ah(async (req, res) => {
      const { ids } = CompararQuerySchema.parse(req.query);
      const encontrados = await prisma.jugador.findMany({
        where: { id: { in: ids } },
        select: REF_JUGADOR,
      });
      if (encontrados.length !== ids.length) throw notFound("Jugador");
      const deporte = encontrados[0]!.deporte;
      if (encontrados.some((j) => j.deporte !== deporte)) {
        throw new AppError("VALIDATION_ERROR", 400, "Los jugadores deben ser del mismo deporte");
      }
      const rutas = metricasNumericas(deporte, schemasDir);
      const porId = new Map(encontrados.map((j) => [j.id, j]));
      // Sequential on purpose: one player's queries at a time keeps the connection pool calm.
      const jugadores = [];
      for (const id of ids) {
        const resumen = await promediosJugador(prisma, id, rutas);
        jugadores.push({ jugador: porId.get(id)!, ...resumen });
      }
      res.json({ deporte, jugadores });
    }),
  );

  router.get(
    "/:id/promedios",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const { ultimos } = PromediosQuerySchema.parse(req.query);
      const jugador = await prisma.jugador.findUnique({ where: { id }, select: REF_JUGADOR });
      if (!jugador) throw notFound("Jugador");
      const rutas = metricasNumericas(jugador.deporte, schemasDir);
      const resumen = await promediosJugador(prisma, id, rutas, ultimos);
      res.json({ jugador, ultimos: ultimos ?? null, ...resumen });
    }),
  );

  router.get(
    "/:id/tendencia",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const { metrica, n } = TendenciaQuerySchema.parse(req.query);
      const jugador = await prisma.jugador.findUnique({ where: { id }, select: REF_JUGADOR });
      if (!jugador) throw notFound("Jugador");
      const rutas = metricasNumericas(jugador.deporte, schemasDir);
      if (!rutas.includes(metrica)) {
        throw new AppError("VALIDATION_ERROR", 400, "Métrica desconocida para el deporte", {
          metricasValidas: rutas,
        });
      }
      const serie = await tendenciaJugador(prisma, id, metrica, n);
      res.json({ jugadorId: id, metrica, n, serie });
    }),
  );

  router.use(
    createCrudRouter({
      name: "Jugador",
      delegate: prisma.jugador,
      createSchema: CreateJugadorSchema,
      updateSchema: UpdateJugadorSchema,
      filterSchema: JugadorFilterSchema,
      where: (f) => ({
        ...(f.deporte ? { deporte: f.deporte } : {}),
        ...(f.q ? { nombre: { contains: f.q, mode: "insensitive" } } : {}),
      }),
      orderBy: { nombre: "asc" },
      include: { equipo: { select: { id: true, nombre: true, abreviatura: true } } },
      writeGuard: adminOnly,
    }),
  );
  return router;
}

/** /api/partidos · filters ?fecha= (YYYY-MM-DD, UTC day) and ?jornada= · GET /:id/boxscore */
export function partidosRouter({ prisma, adminOnly }: Deps): Router {
  const router = Router();

  router.get(
    "/:id/boxscore",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const partido = await prisma.partido.findUnique({
        where: { id },
        include: {
          local: { select: { id: true, nombre: true, abreviatura: true } },
          visita: { select: { id: true, nombre: true, abreviatura: true } },
          estadisticas: {
            include: { jugador: { select: { id: true, nombre: true, posicion: true } } },
          },
        },
      });
      if (!partido) throw notFound("Partido");
      const { estadisticas, ...resto } = partido;
      res.json({
        partido: resto,
        local: estadisticas.filter((e) => e.equipoId === partido.localId),
        visita: estadisticas.filter((e) => e.equipoId === partido.visitaId),
      });
    }),
  );

  router.use(
    createCrudRouter({
      name: "Partido",
      delegate: prisma.partido,
      createSchema: CreatePartidoSchema,
      updateSchema: UpdatePartidoSchema,
      filterSchema: PartidoFilterSchema,
      where: (f) => {
        const where: Prisma.PartidoWhereInput = {};
        if (f.jornada) where.jornada = f.jornada;
        if (f.fecha) {
          const inicio = new Date(`${f.fecha}T00:00:00.000Z`);
          where.fecha = { gte: inicio, lt: new Date(inicio.getTime() + 86_400_000) };
        }
        return where;
      },
      orderBy: { fecha: "asc" },
      include: {
        local: { select: { id: true, nombre: true, abreviatura: true } },
        visita: { select: { id: true, nombre: true, abreviatura: true } },
      },
      writeGuard: adminOnly,
    }),
  );
  return router;
}
