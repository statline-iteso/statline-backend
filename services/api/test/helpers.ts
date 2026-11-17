import type { PrismaClient } from "@prisma/client";
import { mockDeep, type DeepMockProxy } from "jest-mock-extended";
import pino from "pino";
import { createApp } from "../src/app";
import { createTokenService, type Rol } from "../src/lib/auth";
import { createMetrics } from "../src/lib/metrics";
import type { PrediccionesClient } from "../src/lib/predicciones";

export const tokens = createTokenService({
  accessSecret: "test-access-secret-0123456789",
  refreshSecret: "test-refresh-secret-0123456789",
  accessTtl: "5m",
  refreshTtl: "1h",
});

export function buildApp() {
  const prisma = mockDeep<PrismaClient>() as DeepMockProxy<PrismaClient>;
  const predicciones = mockDeep<PrediccionesClient>() as DeepMockProxy<PrediccionesClient>;
  const app = createApp({
    prisma: prisma as unknown as PrismaClient,
    tokens,
    metrics: createMetrics(),
    logger: pino({ level: "silent" }),
    predicciones,
  });
  return { app, prisma, predicciones };
}

export const USER_ID = "11111111-1111-4111-8111-111111111111";
export const ADMIN_ID = "22222222-2222-4222-8222-222222222222";

export const bearer = (rol: Rol = "USUARIO", sub = rol === "ADMIN" ? ADMIN_ID : USER_ID) =>
  `Bearer ${tokens.signAccess({ sub, rol })}`;
