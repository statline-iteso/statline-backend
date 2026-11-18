import Redis from "ioredis";
import type { Logger } from "pino";

export interface RedisHandle {
  /** ioredis client. The offline queue is disabled: commands fail fast while Redis is down. */
  client: Redis;
  /** PING with a timeout. Rejects when Redis is unreachable or does not answer in time. */
  ping(timeoutMs?: number): Promise<void>;
  /** Closes the connection (QUIT, or a forced disconnect if QUIT fails). */
  close(): Promise<void>;
}

/**
 * Creates the Redis client. Called only when REDIS_URL is set. The connection is lazy: nothing
 * connects until the first command, and reconnects use capped exponential backoff. Errors are
 * logged, never thrown into requests; callers treat any failure as "cache miss / memory fallback".
 */
export function createRedis(url: string, logger: Logger): RedisHandle {
  const client = new Redis(url, {
    lazyConnect: true,
    enableOfflineQueue: false,
    maxRetriesPerRequest: 1,
    connectTimeout: 2000,
    retryStrategy: (attempt) => Math.min(200 * 2 ** attempt, 10_000),
  });
  // Without a listener ioredis would throw on every connection error.
  client.on("error", (err: Error) => logger.warn({ err: err.message }, "redis connection error"));

  return {
    client,
    async ping(timeoutMs = 500) {
      const run =
        client.status === "wait" ? client.connect().then(() => client.ping()) : client.ping();
      await withTimeout(run, timeoutMs, "redis ping timed out");
    },
    async close() {
      if (client.status === "end") return;
      try {
        await client.quit();
      } catch {
        client.disconnect();
      }
    },
  };
}

/** Rejects with `message` if `promise` has not settled within `ms`. */
export function withTimeout<T>(promise: Promise<T>, ms: number, message = "timed out"): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
