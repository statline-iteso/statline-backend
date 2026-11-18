import { Router } from "express";
import { ah } from "../lib/async";
import type { Metrics } from "../lib/metrics";

export interface HealthDeps {
  /** Resolves when the database answers; rejects otherwise. */
  pingDb: () => Promise<void>;
  /** Only passed when REDIS_URL is set; readiness then also requires Redis. */
  pingRedis?: () => Promise<void>;
  metrics: Metrics;
}

/** /healthz (liveness), /readyz (readiness) and /metrics (Prometheus), proposal §2.2. */
export function healthRouter({ pingDb, pingRedis, metrics }: HealthDeps): Router {
  const router = Router();

  router.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });

  router.get(
    "/readyz",
    ah(async (_req, res) => {
      const probes: Array<[string, () => Promise<void>]> = [["db", pingDb]];
      if (pingRedis) probes.push(["redis", pingRedis]);
      const results = await Promise.all(
        probes.map(async ([name, probe]) => {
          try {
            await probe();
            return [name, "ok"] as const;
          } catch {
            return [name, "down"] as const;
          }
        }),
      );
      const checks = Object.fromEntries(results);
      const ready = results.every(([, state]) => state === "ok");
      res.status(ready ? 200 : 503).json({
        status: ready ? "ready" : "not_ready",
        checks,
      });
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
