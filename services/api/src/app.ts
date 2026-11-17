import express, { type Express } from "express";
import helmet from "helmet";
import pinoHttp from "pino-http";
import type { Logger } from "pino";
import type { PrismaClient } from "@prisma/client";
import type { TokenService } from "./lib/auth";
import type { Metrics } from "./lib/metrics";
import { requireAuth, requireRole } from "./middleware/auth";
import { errorHandler, notFoundHandler } from "./middleware/error-handler";
import { healthRouter } from "./routes/health";
import { authRouter, usuariosRouter } from "./routes/usuarios";
import { equiposRouter, jugadoresRouter, ligasRouter, partidosRouter } from "./routes/catalogo";
import { alertasRouter } from "./routes/alertas";
import { ingestasRouter } from "./routes/ingestas";
import { crearLanzadorDeshabilitado, type LanzadorIngesta } from "./lib/ingesta-lanzador";

export interface AppDeps {
  prisma: PrismaClient;
  tokens: TokenService;
  metrics: Metrics;
  logger: Logger;
  /** Manual ingestion launcher; defaults to the disabled one (503). */
  lanzador?: LanzadorIngesta;
}

/** Composition root for HTTP. server.ts wires real dependencies; tests pass fakes. */
export function createApp(deps: AppDeps): Express {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", 1); // ingress-nginx

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

  app.use(
    healthRouter({
      pingDb: async () => {
        await deps.prisma.$queryRaw`SELECT 1`;
      },
      metrics: deps.metrics,
    }),
  );

  const auth = requireAuth(deps.tokens);
  const adminOnly = requireRole("ADMIN");
  const catalogo = { prisma: deps.prisma, adminOnly };

  app.use("/api/auth", authRouter(deps));
  app.use("/api/usuarios", usuariosRouter({ prisma: deps.prisma, auth }));
  app.use("/api/ligas", auth, ligasRouter(catalogo));
  app.use("/api/equipos", auth, equiposRouter(catalogo));
  app.use("/api/jugadores", auth, jugadoresRouter(catalogo));
  app.use("/api/partidos", auth, partidosRouter(catalogo));
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
  // TODO(SL-28..SL-29): /api/estadisticas, /api/listas, /api/pronosticos, /api/proyecciones,
  // /api/modelos (docs/ARCHITECTURE.md §3.2).

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

const isProbe = (url = "") =>
  url.startsWith("/healthz") || url.startsWith("/readyz") || url.startsWith("/metrics");
