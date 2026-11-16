import { Router, type RequestHandler } from "express";
import type { PrismaClient } from "@prisma/client";
import { ah } from "../lib/async";
import { hashPassword, verifyPassword, type Claims, type TokenService } from "../lib/auth";
import { forbidden, notFound, unauthorized } from "../lib/errors";
import { IdParamSchema, PaginationSchema } from "../lib/crud";
import { requireRole } from "../middleware/auth";
import { CreateUsuarioSchema, LoginSchema, RefreshSchema, UpdateUsuarioSchema } from "./schemas";

/** Fields returned to clients; never the password hash. */
const PUBLIC_FIELDS = {
  id: true,
  email: true,
  nombre: true,
  rol: true,
  creadoEn: true,
  actualizadoEn: true,
} as const;

/** POST /api/auth/login and POST /api/auth/refresh. */
export function authRouter(deps: { prisma: PrismaClient; tokens: TokenService }): Router {
  const router = Router();

  router.post(
    "/login",
    ah(async (req, res) => {
      const { email, password } = LoginSchema.parse(req.body);
      const user = await deps.prisma.usuario.findUnique({ where: { email } });
      // Same error for unknown email and wrong password, so emails can't be enumerated.
      if (!user || !(await verifyPassword(password, user.passwordHash))) {
        throw unauthorized("Credenciales inválidas");
      }
      const claims: Claims = { sub: user.id, rol: user.rol };
      res.json({
        accessToken: deps.tokens.signAccess(claims),
        refreshToken: deps.tokens.signRefresh(claims),
        usuario: { id: user.id, email: user.email, nombre: user.nombre, rol: user.rol },
      });
    }),
  );

  router.post(
    "/refresh",
    ah(async (req, res) => {
      const { refreshToken } = RefreshSchema.parse(req.body);
      const { sub } = deps.tokens.verifyRefresh(refreshToken);
      // Re-read the role so a demoted user does not keep old privileges.
      const user = await deps.prisma.usuario.findUnique({ where: { id: sub } });
      if (!user) throw unauthorized();
      const claims: Claims = { sub: user.id, rol: user.rol };
      res.json({
        accessToken: deps.tokens.signAccess(claims),
        refreshToken: deps.tokens.signRefresh(claims),
      });
    }),
  );

  return router;
}

/**
 * /api/usuarios. POST is public (sign-up, always role USUARIO). Listing and deleting are
 * ADMIN only; a user can read and update only their own record unless they are ADMIN.
 */
export function usuariosRouter(deps: { prisma: PrismaClient; auth: RequestHandler }): Router {
  const router = Router();
  const { prisma, auth } = deps;

  const selfOrAdmin: RequestHandler = (req, res, next) => {
    const user = res.locals.user as Claims;
    if (user.rol !== "ADMIN" && user.sub !== req.params.id) return next(forbidden());
    next();
  };

  router.post(
    "/",
    ah(async (req, res) => {
      const { email, nombre, password } = CreateUsuarioSchema.parse(req.body);
      const usuario = await prisma.usuario.create({
        data: { email, nombre, passwordHash: await hashPassword(password) },
        select: PUBLIC_FIELDS,
      });
      res.status(201).json(usuario);
    }),
  );

  router.get(
    "/",
    auth,
    requireRole("ADMIN"),
    ah(async (req, res) => {
      const { page, pageSize } = PaginationSchema.parse(req.query);
      const [data, total] = await Promise.all([
        prisma.usuario.findMany({
          select: PUBLIC_FIELDS,
          orderBy: { creadoEn: "desc" },
          skip: (page - 1) * pageSize,
          take: pageSize,
        }),
        prisma.usuario.count(),
      ]);
      res.json({ data, total, page, pageSize });
    }),
  );

  router.get(
    "/:id",
    auth,
    selfOrAdmin,
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const usuario = await prisma.usuario.findUnique({ where: { id }, select: PUBLIC_FIELDS });
      if (!usuario) throw notFound("Usuario");
      res.json(usuario);
    }),
  );

  router.put(
    "/:id",
    auth,
    selfOrAdmin,
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      const { nombre, password, rol } = UpdateUsuarioSchema.parse(req.body);
      if (rol && (res.locals.user as Claims).rol !== "ADMIN") throw forbidden();
      const usuario = await prisma.usuario.update({
        where: { id },
        data: {
          nombre,
          rol,
          passwordHash: password ? await hashPassword(password) : undefined,
        },
        select: PUBLIC_FIELDS,
      });
      res.json(usuario);
    }),
  );

  router.delete(
    "/:id",
    auth,
    requireRole("ADMIN"),
    ah(async (req, res) => {
      const { id } = IdParamSchema.parse(req.params);
      await prisma.usuario.delete({ where: { id } });
      res.status(204).end();
    }),
  );

  return router;
}
