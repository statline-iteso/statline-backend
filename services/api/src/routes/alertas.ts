import { Router } from "express";
import { Prisma, type PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { IdParamSchema, PaginationSchema } from "../lib/crud";
import { AppError, forbidden, notFound } from "../lib/errors";
import type { Claims } from "../lib/auth";
import { CreateAlertaSchema, UpdateAlertaSchema } from "./schemas";

interface Deps {
  prisma: PrismaClient;
}

interface Referencias {
  jugadorId?: string;
  equipoId?: string;
}

/** The referenced jugador/equipo must exist; otherwise 400 with the offending field. */
async function verificarReferencias(prisma: PrismaClient, ref: Referencias): Promise<void> {
  const errores: Array<{ path: string; message: string }> = [];
  if (ref.jugadorId) {
    const jugador = await prisma.jugador.findUnique({
      where: { id: ref.jugadorId },
      select: { id: true },
    });
    if (!jugador) errores.push({ path: "jugadorId", message: "El jugador no existe" });
  }
  if (ref.equipoId) {
    const equipo = await prisma.equipo.findUnique({
      where: { id: ref.equipoId },
      select: { id: true },
    });
    if (!equipo) errores.push({ path: "equipoId", message: "El equipo no existe" });
  }
  if (errores.length > 0) {
    throw new AppError("VALIDATION_ERROR", 400, "Solicitud inválida", errores);
  }
}

/** Prisma needs an explicit DbNull to clear a nullable JSONB column. */
const condicionDb = (condicion: unknown): Prisma.InputJsonValue | typeof Prisma.DbNull =>
  condicion === undefined || condicion === null
    ? Prisma.DbNull
    : (condicion as Prisma.InputJsonValue);

/**
 * /api/alertas. Every alert belongs to the user in the JWT (`usuarioId`). Non-admins only see
 * and change their own alerts; ADMIN can list and read all of them, but still changes only
 * their own. Non-owners get 403.
 */
export function alertasRouter({ prisma }: Deps): Router {
  const router = Router();
  const usuarioDe = (res: { locals: Record<string, unknown> }) => res.locals.user as Claims;

  /** Loads the alert and checks ownership; `lectura` lets ADMIN read any alert. */
  async function cargar(
    req: { params: unknown },
    res: { locals: Record<string, unknown> },
    lectura: boolean,
  ) {
    const { id } = IdParamSchema.parse(req.params);
    const alerta = await prisma.alerta.findUnique({ where: { id } });
    if (!alerta) throw notFound("Alerta");
    const user = usuarioDe(res);
    const esDueno = alerta.usuarioId === user.sub;
    if (!esDueno && !(lectura && user.rol === "ADMIN")) throw forbidden();
    return alerta;
  }

  router.get(
    "/",
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const user = usuarioDe(res);
      const where = user.rol === "ADMIN" ? {} : { usuarioId: user.sub };
      const [data, total] = await Promise.all([
        prisma.alerta.findMany({
          where,
          orderBy: { creadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
        }),
        prisma.alerta.count({ where }),
      ]);
      res.json({ data, total, page, pageSize });
    }),
  );

  router.get(
    "/:id",
    ah(async (req, res) => {
      res.json(await cargar(req, res, true));
    }),
  );

  router.post(
    "/",
    ah(async (req, res) => {
      const body = CreateAlertaSchema.parse(req.body);
      await verificarReferencias(prisma, body);
      const alerta = await prisma.alerta.create({
        data: {
          usuarioId: usuarioDe(res).sub,
          tipo: body.tipo,
          jugadorId: body.jugadorId ?? null,
          equipoId: "equipoId" in body ? (body.equipoId ?? null) : null,
          condicion: condicionDb("condicion" in body ? body.condicion : null),
          activa: body.activa ?? true,
        },
      });
      res.status(201).json(alerta);
    }),
  );

  router.put(
    "/:id",
    ah(async (req, res) => {
      const alerta = await cargar(req, res, false);
      const body = UpdateAlertaSchema.parse(req.body);
      if (!("tipo" in body)) {
        res.json(
          await prisma.alerta.update({ where: { id: alerta.id }, data: { activa: body.activa } }),
        );
        return;
      }
      await verificarReferencias(prisma, body);
      res.json(
        await prisma.alerta.update({
          where: { id: alerta.id },
          data: {
            tipo: body.tipo,
            jugadorId: body.jugadorId ?? null,
            equipoId: "equipoId" in body ? (body.equipoId ?? null) : null,
            condicion: condicionDb("condicion" in body ? body.condicion : null),
            ...(body.activa === undefined ? {} : { activa: body.activa }),
          },
        }),
      );
    }),
  );

  router.delete(
    "/:id",
    ah(async (req, res) => {
      const alerta = await cargar(req, res, false);
      await prisma.alerta.delete({ where: { id: alerta.id } });
      res.status(204).end();
    }),
  );

  return router;
}
