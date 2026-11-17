import { PrismaClient } from "@prisma/client";
import pino from "pino";
import { createApp } from "./app";
import { loadConfig } from "./config";
import { createTokenService } from "./lib/auth";
import { createMetrics } from "./lib/metrics";
import { createMetricasValidator } from "./lib/metricas";

const config = loadConfig();
const logger = pino({ level: config.LOG_LEVEL });
const prisma = new PrismaClient();

const app = createApp({
  prisma,
  logger,
  metrics: createMetrics(),
  metricas: createMetricasValidator(config.SCHEMAS_DIR),
  tokens: createTokenService({
    accessSecret: config.JWT_SECRET,
    refreshSecret: config.JWT_REFRESH_SECRET,
    accessTtl: config.JWT_ACCESS_TTL,
    refreshTtl: config.JWT_REFRESH_TTL,
  }),
});

const server = app.listen(config.PORT, () => logger.info({ port: config.PORT }, "api listening"));

// Kubernetes sends SIGTERM before killing the pod: stop accepting, drain, then disconnect.
const shutdown = (signal: string) => {
  logger.info({ signal }, "shutting down");
  server.close(() => {
    void prisma.$disconnect().finally(() => process.exit(0));
  });
  setTimeout(() => process.exit(1), 10_000).unref();
};
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
