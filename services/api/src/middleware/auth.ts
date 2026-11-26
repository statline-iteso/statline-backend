import type { RequestHandler } from "express";
import type { Claims, Rol } from "../lib/auth";
import type { Autenticador } from "../lib/cognito";
import { forbidden, unauthorized } from "../lib/errors";

/** Bearer token → res.locals.user. The autenticador is local JWT or Cognito (AUTH_MODE). */
export function requireAuth(autenticar: Autenticador): RequestHandler {
  return (req, res, next) => {
    const [scheme, token] = (req.header("authorization") ?? "").split(" ");
    if (scheme !== "Bearer" || !token) return next(unauthorized());
    autenticar(token).then(
      (claims) => {
        res.locals.user = claims;
        next();
      },
      (err: unknown) => next(err),
    );
  };
}

export function requireRole(...roles: Rol[]): RequestHandler {
  return (_req, res, next) => {
    const user = res.locals.user as Claims | undefined;
    if (!user || !roles.includes(user.rol)) return next(forbidden());
    next();
  };
}
