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
import type { MetricasValidator } from "./lib/metricas";
import { requireAuth, requireRole } from "./middleware/auth";
import { errorHandler, notFoundHandler } from "./middleware/error-handler";
import { healthRouter } from "./routes/health";
import { authRouter, usuariosRouter } from "./routes/usuarios";
import { equiposRouter, jugadoresRouter, ligasRouter, partidosRouter } from "./routes/catalogo";
import { estadisticasRouter } from "./routes/estadisticas";
import { listasRouter } from "./routes/listas";
import { alertasRouter } from "./routes/alertas";
import { ingestasRouter } from "./routes/ingestas";
import { crearLanzadorDeshabilitado, type LanzadorIngesta } from "./lib/ingesta-lanzador";
import { modelosRouter, pronosticosRouter, proyeccionesRouter } from "./routes/predicciones";
import type { PrediccionesClient } from "./lib/predicciones";
import type { Autenticador } from "./lib/cognito";

export interface AppDeps {
  prisma: PrismaClient;
  tokens: TokenService;
  metrics: Metrics;
  /** Validates EstadisticaJugadorPartido.metricas against schemas/<deporte>.schema.json. */
  metricas: MetricasValidator;
  logger: Logger;
  /** Shared Redis for the catalog cache and rate limits. Undefined when REDIS_URL is unset. */
  redis?: RedisHandle;
  /** Catalog cache TTL in seconds (CACHE_TTL_S). */
  cacheTtlS?: number;
  /** Requests per minute per client IP (RATE_LIMIT_PER_MIN and RATE_LIMIT_LOGIN_PER_MIN). */
  rateLimits?: { global: number; login: number };
  /** Directory with the metric JSON Schemas (SCHEMAS_DIR); defaults to the repo's schemas/. */
  schemasDir?: string;
  /** Manual ingestion launcher; defaults to the disabled one (503). */
  lanzador?: LanzadorIngesta;
  predicciones: PrediccionesClient;
  /**
   * Cognito mode (AUTH_MODE=cognito, D-47): verifies Cognito ID tokens. Unset: local mode, our own
   * JWTs from `tokens`. In Cognito mode /api/auth/* and the public sign-up answer 404.
   */
  cognito?: Autenticador;
}

/** Composition root for HTTP. server.ts wires real dependencies; tests pass fakes. */
export function createApp(deps: AppDeps): Express {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // exactly one proxy hop (ingress-nginx); see docs/ARCHITECTURE.md §3.5

  app.use(helmet());
  app.use(pinoHttp({ logger: deps.logger, autoLogging: { ignore: (req) => isProbe(req.url) } }));
  app.use(express.json({ limit: "1mb" })); // room for a 500-line lote

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

  const autenticar: Autenticador =
    deps.cognito ?? ((token) => Promise.resolve().then(() => deps.tokens.verifyAccess(token)));
  const auth = requireAuth(autenticar);
  const adminOnly = requireRole("ADMIN");
  const cache = createCatalogCache({
    redis: redis?.client,
    ttlS: deps.cacheTtlS ?? 60,
    metrics: deps.metrics,
    logger: deps.logger,
  });
  const catalogo = { prisma: deps.prisma, adminOnly, cache };

  const cognito = deps.cognito !== undefined;
  if (!cognito) app.use("/api/auth", authRouter(deps));
  app.use("/api/usuarios", usuariosRouter({ prisma: deps.prisma, auth, cognito }));
  app.use("/api/ligas", auth, ligasRouter(catalogo));
  app.use("/api/equipos", auth, equiposRouter(catalogo));
  app.use("/api/jugadores", auth, jugadoresRouter({ ...catalogo, schemasDir: deps.schemasDir }));
  app.use("/api/partidos", auth, partidosRouter(catalogo));
  app.use(
    "/api/estadisticas",
    auth,
    estadisticasRouter({ prisma: deps.prisma, adminOnly, metricas: deps.metricas }),
  );
  app.use("/api/listas", auth, listasRouter({ prisma: deps.prisma }));
  app.use("/api/alertas", auth, alertasRouter({ prisma: deps.prisma }));
  app.use(
    "/api/ingestas",
    auth,
    adminOnly,
    ingestasRouter({
      prisma: deps.prisma,
      adminOnly,
      lanzador: deps.lanzador ?? crearLanzadorDeshabilitado(),
    }),
  );
  const predicciones = { prisma: deps.prisma, predicciones: deps.predicciones };
  app.use("/api/pronosticos", auth, pronosticosRouter(predicciones));
  app.use("/api/proyecciones", auth, proyeccionesRouter(predicciones));
  app.use("/api/modelos", auth, modelosRouter(predicciones));

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

const isProbe = (url = "") =>
  url.startsWith("/healthz") || url.startsWith("/readyz") || url.startsWith("/metrics");
