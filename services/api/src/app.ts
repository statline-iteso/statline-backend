import express, { type Express } from "express";
import helmet from "helmet";
import pinoHttp from "pino-http";
import type { Logger } from "pino";
import type { PrismaClient } from "@prisma/client";
import type { TokenService } from "./lib/auth";
import type { Metrics } from "./lib/metrics";
import { createCatalogCache } from "./lib/cache";
import { createRateLimiters } from "./lib/rate-limit";
import type { RedisHandle } from "./lib/redis";
import { requireAuth, requireRole } from "./middleware/auth";
import { errorHandler, notFoundHandler } from "./middleware/error-handler";
import { healthRouter } from "./routes/health";
import { authRouter, usuariosRouter } from "./routes/usuarios";
import { equiposRouter, jugadoresRouter, ligasRouter, partidosRouter } from "./routes/catalogo";

export interface AppDeps {
  prisma: PrismaClient;
  tokens: TokenService;
  metrics: Metrics;
  logger: Logger;
  /** Shared Redis for the catalog cache and rate limits. Undefined when REDIS_URL is unset. */
  redis?: RedisHandle;
  /** Catalog cache TTL in seconds (CACHE_TTL_S). */
  cacheTtlS?: number;
  /** Requests per minute per client IP (RATE_LIMIT_PER_MIN and RATE_LIMIT_LOGIN_PER_MIN). */
  rateLimits?: { global: number; login: number };
  /** Directory with the metric JSON Schemas (SCHEMAS_DIR); defaults to the repo's schemas/. */
  schemasDir?: string;
}

/** Composition root for HTTP. server.ts wires real dependencies; tests pass fakes. */
export function createApp(deps: AppDeps): Express {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // exactly one proxy hop (ingress-nginx); see docs/ARCHITECTURE.md §3.5

  app.use(helmet());
  app.use(pinoHttp({ logger: deps.logger, autoLogging: { ignore: (req) => isProbe(req.url) } }));
  app.use(express.json({ limit: "100kb" }));

  app.use((req, res, next) => {
    const end = deps.metrics.httpDuration.startTimer({ method: req.method });
    res.on("finish", () => {
      const route = req.route?.path ? `${req.baseUrl}${req.route.path}` : "unmatched";
      deps.metrics.httpRequests.inc({ method: req.method, route, status: res.statusCode });
      end({ route });
    });
    next();
  });

  const redis = deps.redis;
  app.use(
    healthRouter({
      pingDb: async () => {
        await deps.prisma.$queryRaw`SELECT 1`;
      },
      pingRedis: redis && (() => redis.ping()),
      metrics: deps.metrics,
    }),
  );

  // Probes and /metrics sit outside /api, so they are never rate limited.
  const limiters = createRateLimiters({
    redis: redis?.client,
    globalPerMin: deps.rateLimits?.global ?? 300,
    loginPerMin: deps.rateLimits?.login ?? 10,
    logger: deps.logger,
  });
  app.use("/api", limiters.global);
  app.post("/api/auth/login", limiters.login);

  const auth = requireAuth(deps.tokens);
  const adminOnly = requireRole("ADMIN");
  const cache = createCatalogCache({
    redis: redis?.client,
    ttlS: deps.cacheTtlS ?? 60,
    metrics: deps.metrics,
    logger: deps.logger,
  });
  const catalogo = { prisma: deps.prisma, adminOnly, cache };

  app.use("/api/auth", authRouter(deps));
  app.use("/api/usuarios", usuariosRouter({ prisma: deps.prisma, auth }));
  app.use("/api/ligas", auth, ligasRouter(catalogo));
  app.use("/api/equipos", auth, equiposRouter(catalogo));
  app.use("/api/jugadores", auth, jugadoresRouter({ ...catalogo, schemasDir: deps.schemasDir }));
  app.use("/api/partidos", auth, partidosRouter(catalogo));
  // TODO(SL-28..SL-30): /api/estadisticas, /api/listas, /api/pronosticos, /api/proyecciones,
  // /api/modelos, /api/alertas, /api/ingestas (docs/ARCHITECTURE.md §5).

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

const isProbe = (url = "") =>
  url.startsWith("/healthz") || url.startsWith("/readyz") || url.startsWith("/metrics");
