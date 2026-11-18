import { Router, type RequestHandler } from "express";
import type { Deporte, Prisma, PrismaClient } from "@prisma/client";
import type { z } from "zod";
import { ah } from "../lib/async";
import { createCrudRouter, IdParamSchema } from "../lib/crud";
import { AppError, notFound } from "../lib/errors";
import type { ErrorMetrica, MetricasValidator } from "../lib/metricas";
import {
  CreateEstadisticaSchema,
  EstadisticaFilterSchema,
  LoteSchema,
  UpdateEstadisticaSchema,
} from "./schemas";

interface Deps {
  prisma: PrismaClient;
  /** Guard for every write: box scores come from ingestion, so only ADMIN writes them. */
  adminOnly: RequestHandler;
  metricas: MetricasValidator;
}

type Linea = z.infer<typeof CreateEstadisticaSchema>;
type ErrorLinea = ErrorMetrica & { index: number };

const INCLUDE = { jugador: { select: { id: true, nombre: true, posicion: true } } };

/** The sport of a line is the sport of its partido's liga. */
async function deporteDePartido(prisma: PrismaClient, partidoId: string): Promise<Deporte> {
  const partido = await prisma.partido.findUnique({
    where: { id: partidoId },
    select: { liga: { select: { deporte: true } } },
  });
  if (!partido) throw notFound("Partido");
  return partido.liga.deporte;
}

function validarOrThrow(
  validator: MetricasValidator,
  deporte: Deporte,
  metricas: Record<string, unknown>,
): void {
  const errores = validator.validar(deporte, metricas);
  if (errores.length > 0) {
    throw new AppError("VALIDATION_ERROR", 400, "Métricas inválidas", errores);
  }
}

const aDatos = (linea: Linea, deporte: Deporte) => ({
  ...linea,
  deporte,
  metricas: linea.metricas as Prisma.InputJsonObject,
});

/**
 * /api/estadisticas · filters ?jugadorId= and ?partidoId= · POST /lote (ADMIN, up to 500 lines).
 * Every write validates `metricas` against schemas/<deporte>.schema.json (D-06).
 */
export function estadisticasRouter({ prisma, adminOnly, metricas }: Deps): Router {
  const router = Router();

  router.post(
    "/lote",
    adminOnly,
    ah(async (req, res) => {
      const filas = LoteSchema.parse(req.body);
      const errores: ErrorLinea[] = [];
      const lineas: { index: number; linea: Linea }[] = [];

      filas.forEach((fila, index) => {
        const parsed = CreateEstadisticaSchema.safeParse(fila);
        if (parsed.success) {
          lineas.push({ index, linea: parsed.data });
          return;
        }
        for (const issue of parsed.error.issues) {
          errores.push({ index, path: issue.path.join("."), message: issue.message });
        }
      });

      const partidos = await prisma.partido.findMany({
        where: { id: { in: [...new Set(lineas.map((l) => l.linea.partidoId))] } },
        select: { id: true, liga: { select: { deporte: true } } },
      });
      const deportePorPartido = new Map(partidos.map((p) => [p.id, p.liga.deporte]));

      const validas: { linea: Linea; deporte: Deporte }[] = [];
      for (const { index, linea } of lineas) {
        const deporte = deportePorPartido.get(linea.partidoId);
        if (!deporte) {
          errores.push({ index, path: "partidoId", message: "Partido no encontrado" });
          continue;
        }
        for (const e of metricas.validar(deporte, linea.metricas)) {
          errores.push({ index, ...e });
        }
        validas.push({ linea, deporte });
      }

      if (errores.length > 0) {
        errores.sort((a, b) => a.index - b.index);
        throw new AppError("VALIDATION_ERROR", 400, "Lote inválido", errores);
      }

      // All or nothing: a failing upsert rolls back the whole batch.
      const resultados = await prisma.$transaction(
        validas.map(({ linea, deporte }) => {
          const datos = aDatos(linea, deporte);
          return prisma.estadisticaJugadorPartido.upsert({
            where: {
              partidoId_jugadorId: { partidoId: linea.partidoId, jugadorId: linea.jugadorId },
            },
            create: datos,
            update: {
              equipoId: datos.equipoId,
              minutos: datos.minutos,
              deporte: datos.deporte,
              metricas: datos.metricas,
            },
          });
        }),
      );
      res.json({ procesadas: resultados.length, data: resultados });
    }),
  );

  router.post(
    "/",
    adminOnly,
    ah(async (req, res) => {
      const linea = CreateEstadisticaSchema.parse(req.body);
      const deporte = await deporteDePartido(prisma, linea.partidoId);
      validarOrThrow(metricas, deporte, linea.metricas);
      const creada = await prisma.estadisticaJugadorPartido.create({
        data: aDatos(linea, deporte),
        include: INCLUDE,
      });
      res.status(201).json(creada);
    }),
  );

  router.put(
    "/:id",
    adminOnly,
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const cambios = UpdateEstadisticaSchema.parse(req.body);
      const actual = await prisma.estadisticaJugadorPartido.findUnique({ where: { id } });
      if (!actual) throw notFound("Estadística");
      // Re-validate the merged result: a new partido may mean another sport's schema.
      const deporte = await deporteDePartido(prisma, cambios.partidoId ?? actual.partidoId);
      const merged = cambios.metricas ?? (actual.metricas as Record<string, unknown>);
      validarOrThrow(metricas, deporte, merged);
      const actualizada = await prisma.estadisticaJugadorPartido.update({
        where: { id },
        data: { ...cambios, deporte, metricas: merged as Prisma.InputJsonObject },
        include: INCLUDE,
      });
      res.json(actualizada);
    }),
  );

  router.use(
    createCrudRouter({
      name: "Estadística",
      delegate: prisma.estadisticaJugadorPartido,
      createSchema: CreateEstadisticaSchema,
      updateSchema: UpdateEstadisticaSchema,
      filterSchema: EstadisticaFilterSchema,
      where: (f) => ({
        ...(f.jugadorId ? { jugadorId: f.jugadorId } : {}),
        ...(f.partidoId ? { partidoId: f.partidoId } : {}),
      }),
      orderBy: { creadoEn: "desc" },
      include: INCLUDE,
      writeGuard: adminOnly,
      // POST and PUT are above, because they need the sport and the metrics check.
      only: ["list", "get", "delete"],
    }),
  );
  return router;
}
