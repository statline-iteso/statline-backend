import { Router } from "express";
import { ah } from "../lib/async";
import type { Metrics } from "../lib/metrics";

export interface HealthDeps {
  /** Resolves when the database answers; rejects otherwise. */
  pingDb: () => Promise<void>;
  metrics: Metrics;
}

/** /healthz (liveness), /readyz (readiness) and /metrics (Prometheus), proposal §2.2. */
export function healthRouter({ pingDb, metrics }: HealthDeps): Router {
  const router = Router();

  router.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });

  router.get(
    "/readyz",
    ah(async (_req, res) => {
      try {
        await pingDb();
        res.json({ status: "ready", checks: { db: "ok" } });
      } catch {
        res.status(503).json({ status: "not_ready", checks: { db: "down" } });
      }
    }),
  );

  router.get(
    "/metrics",
    ah(async (_req, res) => {
      res.set("Content-Type", metrics.registry.contentType);
      res.send(await metrics.registry.metrics());
    }),
  );

  return router;
}
