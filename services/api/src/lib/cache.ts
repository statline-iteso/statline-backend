import type { RequestHandler, Response } from "express";
import type { Logger } from "pino";
import type Redis from "ioredis";
import { ah } from "./async";
import type { Metrics } from "./metrics";
import { withTimeout } from "./redis";

/** The Redis commands the cache needs; ioredis-mock satisfies it in tests. */
export type RedisLike = Pick<Redis, "get" | "set" | "incr">;

export interface CatalogCache {
  /** Put on a catalog GET route: serves a cached 200 body, or caches the one the handler sends. */
  read: RequestHandler;
  /** Put on a catalog write route: bumps the catalog version after a successful (2xx) write. */
  invalidate: RequestHandler;
}

export interface CatalogCacheOptions {
  /** undefined when REDIS_URL is unset: every request bypasses the cache. */
  redis?: RedisLike;
  ttlS: number;
  metrics: Metrics;
  logger: Logger;
  /** Upper bound for each Redis call; slower calls bypass the cache. */
  timeoutMs?: number;
}

const VERSION_KEY = "statline:cache:catalogo:version";
const KEY_PREFIX = "statline:cache:catalogo";

type EndFn = (...args: unknown[]) => unknown;

/**
 * Catalog response cache with version-based invalidation.
 *
 * Every key embeds the current catalog version (`VERSION_KEY`). A successful write INCRs the
 * version, so all earlier entries become unreachable at once and expire by TTL. Standings, form
 * and box scores depend on several resources, so one catalog-wide version is simpler and more
 * correct than per-resource prefixes (and avoids SCAN). The bump runs before the write response
 * is sent, so the client that made the write never reads its own stale data.
 */
export function createCatalogCache({
  redis,
  ttlS,
  metrics,
  logger,
  timeoutMs = 250,
}: CatalogCacheOptions): CatalogCache {
  const lookups = metrics.cacheRequests;

  if (!redis) {
    const bypass: RequestHandler = (_req, _res, next) => {
      lookups.inc({ result: "bypass" });
      next();
    };
    return { read: bypass, invalidate: (_req, _res, next) => next() };
  }

  const client = redis;
  const call = <T>(promise: Promise<T>) => withTimeout(promise, timeoutMs, "redis timed out");

  const read = ah(async (req, res, next) => {
    let key: string;
    try {
      const version = (await call(client.get(VERSION_KEY))) ?? "0";
      key = `${KEY_PREFIX}:v${version}:${req.method}:${req.originalUrl}`;
      const cached = await call(client.get(key));
      if (cached !== null) {
        lookups.inc({ result: "hit" });
        res.set("X-Cache", "HIT").type("application/json").send(cached);
        return;
      }
    } catch (err) {
      logger.warn({ err: errorMessage(err) }, "catalog cache bypassed");
      lookups.inc({ result: "bypass" });
      next();
      return;
    }

    lookups.inc({ result: "miss" });
    res.set("X-Cache", "MISS");
    const json = res.json.bind(res) as Response["json"];
    res.json = ((body: unknown) => {
      // Only successful bodies are cached; errors and 404s are never stored.
      const payload = res.statusCode === 200 ? JSON.stringify(body) : undefined;
      if (payload !== undefined) {
        call(client.set(key, payload, "EX", ttlS)).catch((err: unknown) =>
          logger.warn({ err: errorMessage(err) }, "catalog cache write failed"),
        );
      }
      return json(body);
    }) as Response["json"];
    next();
  });

  const invalidate: RequestHandler = (_req, res, next) => {
    // Hook res.end so the version is bumped before the response reaches the client.
    const end = res.end.bind(res) as unknown as EndFn;
    let bumped = false;
    res.end = ((...args: unknown[]) => {
      if (!bumped && res.statusCode >= 200 && res.statusCode < 300) {
        bumped = true;
        call(client.incr(VERSION_KEY))
          .catch((err: unknown) =>
            logger.warn({ err: errorMessage(err) }, "catalog cache invalidation failed"),
          )
          .finally(() => end(...args));
        return res;
      }
      return end(...args);
    }) as unknown as Response["end"];
    next();
  };

  return { read, invalidate };
}

const errorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err));
