import { Router, type Response } from "express";
import type { Prisma, PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { IdParamSchema, PaginationSchema } from "../lib/crud";
import { notFound } from "../lib/errors";
import type { PrediccionesClient, PrediccionesResponse } from "../lib/predicciones";
import { requireRole } from "../middleware/auth";
import {
  GenerarPronosticosSchema,
  GenerarProyeccionesSchema,
  ModeloFilterSchema,
  PronosticoFilterSchema,
  ProyeccionFilterSchema,
  ReentrenarSchema,
  precisionSchema,
} from "./schemas";

interface Deps {
  prisma: PrismaClient;
  predicciones: PrediccionesClient;
}

const analistaOAdmin = requireRole("ANALISTA", "ADMIN");
const adminOnly = requireRole("ADMIN");

/** Passes predicciones' status and body through unchanged. */
const enviar = (res: Response, r: PrediccionesResponse) => {
  res.status(r.status).json(r.body);
};

const PARTIDO_RESUMEN = {
  select: {
    id: true,
    fecha: true,
    jornada: true,
    estatus: true,
    marcadorLocal: true,
    marcadorVisita: true,
    local: { select: { id: true, nombre: true, abreviatura: true } },
    visita: { select: { id: true, nombre: true, abreviatura: true } },
  },
} as const;

const MODELO_RESUMEN = {
  select: {
    id: true,
    deporte: true,
    tipo: true,
    version: true,
    nombreMetrica: true,
    metricaError: true,
    activo: true,
  },
} as const;

/**
 * /api/pronosticos · filters ?deporte= ?jornada= ?partidoId= · GET /precision · POST /generar
 * GET lists the newest forecast per game (a game can have one per model; re-running a model
 * replaces its rows).
 */
export function pronosticosRouter({ prisma, predicciones }: Deps): Router {
  const router = Router();

  router.get(
    "/",
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const f = PronosticoFilterSchema.parse(req.query);
      const where: Prisma.PronosticoPartidoWhereInput = {};
      const enPartido: Prisma.PartidoWhereInput = {};
      if (f.deporte) enPartido.liga = { deporte: f.deporte };
      if (f.jornada) enPartido.jornada = f.jornada;
      if (Object.keys(enPartido).length > 0) where.partido = enPartido;
      if (f.partidoId) where.partidoId = f.partidoId;
      const [data, todos] = await Promise.all([
        prisma.pronosticoPartido.findMany({
          where,
          distinct: ["partidoId"],
          orderBy: { generadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
          include: { partido: PARTIDO_RESUMEN, modelo: MODELO_RESUMEN },
        }),
        prisma.pronosticoPartido.findMany({ where, distinct: ["partidoId"], select: { id: true } }),
      ]);
      res.json({ data, total: todos.length, page, pageSize });
    }),
  );

  router.get(
    "/precision",
    ah(async (req, res) => {
      const q = precisionSchema("RESULTADO_PARTIDO").parse(req.query);
      enviar(res, await predicciones.get("/precision", { deporte: q.deporte, tipo: q.tipo }));
    }),
  );

  router.post(
    "/generar",
    analistaOAdmin,
    ah(async (req, res) => {
      const body = GenerarPronosticosSchema.parse(req.body);
      enviar(
        res,
        await predicciones.post("/pronosticos/generar", {
          deporte: body.deporte,
          jornada: body.jornada,
          partido_ids: body.partidoIds,
        }),
      );
    }),
  );

  router.get(
    "/:id",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const item = await prisma.pronosticoPartido.findUnique({
        where: { id },
        include: { partido: PARTIDO_RESUMEN, modelo: MODELO_RESUMEN },
      });
      if (!item) throw notFound("Pronóstico");
      res.json(item);
    }),
  );

  return router;
}

/** /api/proyecciones · filters ?jornada= ?jugadorId= ?partidoId= · GET /precision · POST /generar */
export function proyeccionesRouter({ prisma, predicciones }: Deps): Router {
  const router = Router();
  const INCLUDE = {
    jugador: { select: { id: true, nombre: true, posicion: true, equipoId: true } },
    partido: PARTIDO_RESUMEN,
    modelo: MODELO_RESUMEN,
  } as const;

  router.get(
    "/",
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const f = ProyeccionFilterSchema.parse(req.query);
      const where: Prisma.ProyeccionJugadorWhereInput = {};
      if (f.jornada) where.partido = { jornada: f.jornada };
      if (f.jugadorId) where.jugadorId = f.jugadorId;
      if (f.partidoId) where.partidoId = f.partidoId;
      const [data, total] = await Promise.all([
        prisma.proyeccionJugador.findMany({
          where,
          orderBy: { generadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
          include: INCLUDE,
        }),
        prisma.proyeccionJugador.count({ where }),
      ]);
      res.json({ data, total, page, pageSize });
    }),
  );

  router.get(
    "/precision",
    ah(async (req, res) => {
      const q = precisionSchema("PROYECCION_JUGADOR").parse(req.query);
      enviar(res, await predicciones.get("/precision", { deporte: q.deporte, tipo: q.tipo }));
    }),
  );

  router.post(
    "/generar",
    analistaOAdmin,
    ah(async (req, res) => {
      const body = GenerarProyeccionesSchema.parse(req.body);
      enviar(
        res,
        await predicciones.post("/proyecciones/generar", {
          deporte: body.deporte,
          jornada: body.jornada,
          jugador_ids: body.jugadorIds,
        }),
      );
    }),
  );

  router.get(
    "/:id",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const item = await prisma.proyeccionJugador.findUnique({ where: { id }, include: INCLUDE });
      if (!item) throw notFound("Proyección");
      res.json(item);
    }),
  );

  return router;
}

/**
 * /api/modelos · filters ?deporte= ?tipo= · POST /:id/activar (ADMIN, forced) · POST /reentrenar
 * (ADMIN). Only reads are exposed: model rows are created by training and changed by activation.
 * Artifact bytes are never selected (the list returns the ModeloPrediccion scalars only).
 */
export function modelosRouter({ prisma, predicciones }: Deps): Router {
  const router = Router();

  router.get(
    "/",
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const where = ModeloFilterSchema.parse(req.query);
      const [data, total] = await Promise.all([
        prisma.modeloPrediccion.findMany({
          where,
          orderBy: { entrenadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
        }),
        prisma.modeloPrediccion.count({ where }),
      ]);
      res.json({ data, total, page, pageSize });
    }),
  );

  router.post(
    "/reentrenar",
    adminOnly,
    ah(async (req, res) => {
      const body = ReentrenarSchema.parse(req.body);
      enviar(res, await predicciones.post("/modelos/reentrenar", body));
    }),
  );

  router.post(
    "/:id/activar",
    adminOnly,
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      enviar(res, await predicciones.post(`/modelos/${id}/activar`));
    }),
  );

  router.get(
    "/:id",
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const item = await prisma.modeloPrediccion.findUnique({ where: { id } });
      if (!item) throw notFound("Modelo");
      res.json(item);
    }),
  );

  return router;
}
