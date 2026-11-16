import bcrypt from "bcryptjs";
import jwt, { type SignOptions } from "jsonwebtoken";
import { z } from "zod";
import { unauthorized } from "./errors";

export const ROLES = ["ADMIN", "ANALISTA", "USUARIO"] as const;
export type Rol = (typeof ROLES)[number];

const ClaimsSchema = z.object({ sub: z.string(), rol: z.enum(ROLES) });
export type Claims = z.infer<typeof ClaimsSchema>;

export interface TokenService {
  signAccess(claims: Claims): string;
  signRefresh(claims: Claims): string;
  verifyAccess(token: string): Claims;
  verifyRefresh(token: string): Claims;
}

export function createTokenService(opts: {
  accessSecret: string;
  refreshSecret: string;
  accessTtl: string;
  refreshTtl: string;
}): TokenService {
  const sign = (claims: Claims, secret: string, ttl: string) =>
    jwt.sign({ sub: claims.sub, rol: claims.rol }, secret, { expiresIn: ttl } as SignOptions);
  const verify = (token: string, secret: string): Claims => {
    try {
      return ClaimsSchema.parse(jwt.verify(token, secret));
    } catch {
      throw unauthorized();
    }
  };
  return {
    signAccess: (c) => sign(c, opts.accessSecret, opts.accessTtl),
    signRefresh: (c) => sign(c, opts.refreshSecret, opts.refreshTtl),
    verifyAccess: (t) => verify(t, opts.accessSecret),
    verifyRefresh: (t) => verify(t, opts.refreshSecret),
  };
}

const BCRYPT_ROUNDS = 10;
export const hashPassword = (plain: string) => bcrypt.hash(plain, BCRYPT_ROUNDS);
export const verifyPassword = (plain: string, hash: string) => bcrypt.compare(plain, hash);
