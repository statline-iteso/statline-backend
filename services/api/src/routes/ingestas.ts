import { Router, type RequestHandler } from "express";
import type { PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { createCrudRouter } from "../lib/crud";
import type { LanzadorIngesta } from "../lib/ingesta-lanzador";
import { EjecutarIngestaSchema, IngestaFilterSchema } from "./schemas";

interface Deps {
  prisma: PrismaClient;
  /** Mounted behind requireRole("ADMIN") by app.ts; repeated on the write routes. */
  adminOnly: RequestHandler;
  lanzador: LanzadorIngesta;
}

/**
 * /api/ingestas (EjecucionIngesta, ADMIN only). Only GET and DELETE on the audit records;
 * POST /ejecutar starts a manual run through the LanzadorIngesta.
 */
export function ingestasRouter({ prisma, adminOnly, lanzador }: Deps): Router {
  const router = Router();

  router.post(
    "/ejecutar",
    adminOnly,
    ah(async (req, res) => {
      const { deporte } = EjecutarIngestaSchema.parse(req.body);
      const { job } = await lanzador.lanzar(deporte);
      res.status(202).json({ job });
    }),
  );

  router.use(
    createCrudRouter({
      name: "EjecucionIngesta",
      delegate: prisma.ejecucionIngesta,
      createSchema: EjecutarIngestaSchema,
      updateSchema: EjecutarIngestaSchema,
      filterSchema: IngestaFilterSchema,
      where: (f) => ({
        ...(f.deporte ? { deporte: f.deporte } : {}),
        ...(f.estatus ? { estatus: f.estatus } : {}),
      }),
      orderBy: { iniciadaEn: "desc" },
      writeGuard: adminOnly,
      only: ["list", "get", "delete"],
    }),
  );
  return router;
}
