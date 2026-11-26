/**
 * Cognito authentication (AUTH_MODE=cognito, infra D-47). Cognito signs users in; PostgreSQL keeps
 * the Usuario rows and their roles. The SPA sends the Cognito **ID token**; this verifies it against
 * the pool's public keys (fetched once over HTTPS, no IAM needed) and maps it to our Usuario row:
 * by `cognito_sub`, else by verified email (links the seeded admin and pre-Cognito users), else a
 * new USUARIO row. The resulting Claims are the same as in local mode, so routes do not change.
 */
import { Prisma, type PrismaClient } from "@prisma/client";
import { CognitoJwtVerifier } from "aws-jwt-verify";
import type { Claims } from "./auth";
import { unauthorized } from "./errors";

/** What the api needs from a verified ID token. */
export interface IdentidadCognito {
  sub: string;
  email?: string;
  emailVerificado: boolean;
  nombre?: string;
}

/** Verifies a token and returns its identity; throws on an invalid or expired token. */
export type VerificadorCognito = (token: string) => Promise<IdentidadCognito>;

/** Turns a bearer token into Claims. Local mode wraps TokenService.verifyAccess. */
export type Autenticador = (token: string) => Promise<Claims>;

export function crearVerificadorCognito(opts: {
  userPoolId: string;
  clientId: string;
}): VerificadorCognito {
  const verifier = CognitoJwtVerifier.create({
    userPoolId: opts.userPoolId,
    clientId: opts.clientId,
    tokenUse: "id",
  });
  return async (token) => {
    const payload = await verifier.verify(token);
    return identidadDesde(payload);
  };
}

/** Exported for tests that sign their own tokens. */
export function identidadDesde(payload: Record<string, unknown>): IdentidadCognito {
  const texto = (v: unknown) => (typeof v === "string" && v.length > 0 ? v : undefined);
  return {
    sub: String(payload.sub),
    email: texto(payload.email)?.toLowerCase(),
    emailVerificado: payload.email_verified === true || payload.email_verified === "true",
    nombre: texto(payload.name),
  };
}

export function crearAutenticadorCognito(deps: {
  prisma: PrismaClient;
  verificar: VerificadorCognito;
}): Autenticador {
  const { prisma, verificar } = deps;
  const claimsDe = (u: { id: string; rol: Claims["rol"] }): Claims => ({ sub: u.id, rol: u.rol });

  const buscarOCrear = async (id: IdentidadCognito): Promise<Claims> => {
    const porSub = await prisma.usuario.findUnique({ where: { cognitoSub: id.sub } });
    if (porSub) return claimsDe(porSub);
    // Without a verified email Cognito would not have let the user sign in; refuse to be safe.
    if (!id.email || !id.emailVerificado) throw unauthorized("Correo no verificado");

    const porEmail = await prisma.usuario.findUnique({ where: { email: id.email } });
    if (porEmail) {
      const enlazado = await prisma.usuario.update({
        where: { id: porEmail.id },
        data: { cognitoSub: id.sub },
      });
      return claimsDe(enlazado);
    }
    const nuevo = await prisma.usuario.create({
      data: {
        email: id.email,
        nombre: id.nombre ?? id.email.split("@")[0]!,
        cognitoSub: id.sub,
        rol: "USUARIO",
      },
    });
    return claimsDe(nuevo);
  };

  return async (token) => {
    let identidad: IdentidadCognito;
    try {
      identidad = await verificar(token);
    } catch {
      throw unauthorized();
    }
    try {
      return await buscarOCrear(identidad);
    } catch (err) {
      // Two first requests of the same new user race on the insert: the row now exists.
      if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2002") {
        return buscarOCrear(identidad);
      }
      throw err;
    }
  };
}
