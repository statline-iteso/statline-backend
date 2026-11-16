import type { RequestHandler } from "express";
import type { Claims, Rol, TokenService } from "../lib/auth";
import { forbidden, unauthorized } from "../lib/errors";

export function requireAuth(tokens: TokenService): RequestHandler {
  return (req, res, next) => {
    const [scheme, token] = (req.header("authorization") ?? "").split(" ");
    if (scheme !== "Bearer" || !token) return next(unauthorized());
    try {
      res.locals.user = tokens.verifyAccess(token);
      next();
    } catch (err) {
      next(err);
    }
  };
}

export function requireRole(...roles: Rol[]): RequestHandler {
  return (_req, res, next) => {
    const user = res.locals.user as Claims | undefined;
    if (!user || !roles.includes(user.rol)) return next(forbidden());
    next();
  };
}
