import type { PrismaClient } from "@prisma/client";
import { mockDeep, type DeepMockProxy } from "jest-mock-extended";
import pino from "pino";
import { createApp } from "../src/app";
import type { LanzadorIngesta } from "../src/lib/ingesta-lanzador";
import { defaultSchemasDir } from "../src/config";
import { createMetricasValidator } from "../src/lib/metricas";
import { createMetrics } from "../src/lib/metrics";
import { tokens } from "./helpers";

/** App with a custom launcher; the same token service as helpers.ts. */
export function buildAppWithLanzador(lanzador: LanzadorIngesta) {
  const prisma = mockDeep<PrismaClient>() as DeepMockProxy<PrismaClient>;
  const app = createApp({
    prisma: prisma as unknown as PrismaClient,
    tokens,
    metrics: createMetrics(),
    logger: pino({ level: "silent" }),
    metricas: createMetricasValidator(defaultSchemasDir),
    lanzador,
  });
  return { app, prisma };
}
