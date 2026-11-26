// First: Sentry must load before express and http to instrument them.
import "./instrument";
import { PrismaClient } from "@prisma/client";
import pino from "pino";
import { createApp } from "./app";
import { loadConfig } from "./config";
import { createTokenService } from "./lib/auth";
import { createMetrics } from "./lib/metrics";
import { createRedis } from "./lib/redis";
import { createMetricasValidator } from "./lib/metricas";
import { crearLanzadorIngesta } from "./lib/ingesta-lanzador";
import { createPrediccionesClient } from "./lib/predicciones";
import { crearAutenticadorCognito, crearVerificadorCognito } from "./lib/cognito";

const config = loadConfig();
const logger = pino({ level: config.LOG_LEVEL });
const prisma = new PrismaClient();
// Redis is optional: without REDIS_URL the cache is bypassed and limits stay in memory.
const redis = config.REDIS_URL ? createRedis(config.REDIS_URL, logger) : undefined;

// The pool id already names its region (us-east-1_xxx); COGNITO_REGION is informative.
const cognito =
  config.AUTH_MODE === "cognito"
    ? crearAutenticadorCognito({
        prisma,
        verificar: crearVerificadorCognito({
          userPoolId: config.COGNITO_USER_POOL_ID!,
          clientId: config.COGNITO_CLIENT_ID!,
        }),
      })
    : undefined;
logger.info({ authMode: config.AUTH_MODE }, "auth mode");

const app = createApp({
  prisma,
  cognito,
  logger,
  redis,
  cacheTtlS: config.CACHE_TTL_S,
  rateLimits: { global: config.RATE_LIMIT_PER_MIN, login: config.RATE_LIMIT_LOGIN_PER_MIN },
  metrics: createMetrics(),
  schemasDir: config.SCHEMAS_DIR,
  metricas: createMetricasValidator(config.SCHEMAS_DIR),
  lanzador: crearLanzadorIngesta(config.INGESTA_LANZADOR, {
    prefijo: config.INGESTA_CRONJOB_PREFIJO,
  }),
  predicciones: createPrediccionesClient({
    baseUrl: config.PREDICCIONES_URL,
    timeoutMs: config.PREDICCIONES_TIMEOUT_MS,
  }),
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
    void Promise.all([prisma.$disconnect(), redis?.close()]).finally(() => process.exit(0));
  });
  setTimeout(() => process.exit(1), 10_000).unref();
};
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
