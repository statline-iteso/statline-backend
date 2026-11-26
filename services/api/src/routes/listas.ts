import { Router, type Response } from "express";
import type { PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { type Claims } from "../lib/auth";
import { IdParamSchema, PaginationSchema } from "../lib/crud";
import { notFound } from "../lib/errors";
import { CreateListaSchema, ElementoListaSchema, UpdateListaSchema } from "./schemas";

interface Deps {
  prisma: PrismaClient;
}

const userOf = (res: Response) => res.locals.user as Claims;

/**
 * /api/listas: each user, ADMIN included, sees and changes only their own lists. Lists of other
 * users are answered with 404 (not 403) so their ids can't be probed (D-18).
 */
export function listasRouter({ prisma }: Deps): Router {
  const router = Router();

  /** Loads a list the caller owns, or throws 404. */
  async function cargar(
    req: { params: unknown },
    res: Response,
    { incluirElementos = false }: { incluirElementos?: boolean } = {},
  ) {
    const { id } = IdParamSchema.parse(req.params);
    const user = userOf(res);
    const lista = await prisma.listaSeguimiento.findUnique({
      where: { id },
      include: incluirElementos ? { elementos: true } : undefined,
    });
    if (!lista || lista.usuarioId !== user.sub) throw notFound("Lista");
    return lista;
  }

  router.get(
    "/",
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const user = userOf(res);
      const where = { usuarioId: user.sub };
      const [data, total] = await Promise.all([
        prisma.listaSeguimiento.findMany({
          where,
          orderBy: { creadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
        }),
        prisma.listaSeguimiento.count({ where }),
      ]);
      res.json({ data, total, page, pageSize });
    }),
  );

  router.post(
    "/",
    ah(async (req, res) => {
      const { nombre } = CreateListaSchema.parse(req.body);
      const lista = await prisma.listaSeguimiento.create({
        data: { nombre, usuarioId: userOf(res).sub },
      });
      res.status(201).json(lista);
    }),
  );

  router.get(
    "/:id",
    ah(async (req, res) => {
      res.json(await cargar(req, res, { incluirElementos: true }));
    }),
  );

  router.put(
    "/:id",
    ah(async (req, res) => {
      const lista = await cargar(req, res);
      const { nombre } = UpdateListaSchema.parse(req.body);
      res.json(await prisma.listaSeguimiento.update({ where: { id: lista.id }, data: { nombre } }));
    }),
  );

  router.delete(
    "/:id",
    ah(async (req, res) => {
      const lista = await cargar(req, res);
      await prisma.listaSeguimiento.delete({ where: { id: lista.id } });
      res.status(204).end();
    }),
  );

  /** Body { tipo: "JUGADOR" | "EQUIPO", refId }. 404 if the jugador/equipo doesn't exist, 409 if already in the list. */
  router.post(
    "/:id/elementos",
    ah(async (req, res) => {
      const { tipo, refId } = ElementoListaSchema.parse(req.body);
      const lista = await cargar(req, res);
      if (tipo === "JUGADOR") {
        if (!(await prisma.jugador.findUnique({ where: { id: refId }, select: { id: true } }))) {
          throw notFound("Jugador");
        }
      } else if (
        !(await prisma.equipo.findUnique({ where: { id: refId }, select: { id: true } }))
      ) {
        throw notFound("Equipo");
      }
      // The unique key (listaId, tipo, refId) turns a repeat into P2002 -> 409 in the error handler.
      const elemento = await prisma.elementoLista.create({
        data: { listaId: lista.id, tipo, refId },
      });
      res.status(201).json(elemento);
    }),
  );

  /** :ref is the jugador or equipo id (refId), not the elemento id. */
  router.delete(
    "/:id/elementos/:ref",
    ah(async (req, res) => {
      const ref = IdParamSchema.shape.id.parse(req.params.ref);
      const lista = await cargar(req, res);
      const { count } = await prisma.elementoLista.deleteMany({
        where: { listaId: lista.id, refId: ref },
      });
      if (count === 0) throw notFound("Elemento");
      res.status(204).end();
    }),
  );

  return router;
}
