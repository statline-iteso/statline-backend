import type { RequestHandler } from "express";
import {
  MemoryStore,
  rateLimit,
  type IncrementResponse,
  type Options,
  type Store,
} from "express-rate-limit";
import RedisStore, { type RedisReply } from "rate-limit-redis";
import type { Logger } from "pino";
import type Redis from "ioredis";

export interface RateLimiters {
  /** Applied to every /api request (probes and /metrics are outside /api). */
  global: RequestHandler;
  /** Applied to POST /api/auth/login, per client IP. */
  login: RequestHandler;
}

export interface RateLimitOptions {
  /** undefined when REDIS_URL is unset: counters live in process memory. */
  redis?: Pick<Redis, "call">;
  globalPerMin: number;
  loginPerMin: number;
  logger: Logger;
}

/**
 * Redis is the shared store when available; if a call fails, the hit is counted in a per-process
 * memory store instead, so a Redis outage never fails requests. The limit then applies per
 * replica until Redis is back.
 */
export class FailoverStore implements Store {
  readonly localKeys = false;

  constructor(
    private readonly primary: Store,
    private readonly fallback: Store,
    readonly prefix: string,
    private readonly logger: Logger,
  ) {}

  init(options: Options): void {
    void this.primary.init?.(options);
    this.fallback.init?.(options);
  }

  async increment(key: string): Promise<IncrementResponse> {
    try {
      return await this.primary.increment(key);
    } catch (err) {
      this.warn(err);
      return this.fallback.increment(key);
    }
  }

  async decrement(key: string): Promise<void> {
    await this.fallback.decrement(key);
    await this.tryPrimary(() => this.primary.decrement(key));
  }

  async resetKey(key: string): Promise<void> {
    await this.fallback.resetKey(key);
    await this.tryPrimary(() => this.primary.resetKey(key));
  }

  private async tryPrimary(op: () => void | Promise<void>): Promise<void> {
    try {
      await op();
    } catch (err) {
      this.warn(err);
    }
  }

  private warn(err: unknown) {
    this.logger.warn(
      { err: err instanceof Error ? err.message : String(err) },
      "rate-limit store fell back to memory",
    );
  }
}

export function createRateLimiters({
  redis,
  globalPerMin,
  loginPerMin,
  logger,
}: RateLimitOptions): RateLimiters {
  return {
    global: limiter({ prefix: "statline:rl:global:", limit: globalPerMin, redis, logger }),
    login: limiter({ prefix: "statline:rl:login:", limit: loginPerMin, redis, logger }),
  };
}

function limiter(opts: {
  prefix: string;
  limit: number;
  redis?: Pick<Redis, "call">;
  logger: Logger;
}): RequestHandler {
  const memory = new MemoryStore();
  const store = opts.redis
    ? new FailoverStore(
        new RedisStore({ prefix: opts.prefix, sendCommand: redisCommand(opts.redis) }),
        memory,
        opts.prefix,
        opts.logger,
      )
    : memory;
  return rateLimit({
    windowMs: 60_000,
    limit: opts.limit,
    standardHeaders: "draft-7",
    legacyHeaders: false,
    store,
    message: {
      error: { code: "RATE_LIMITED", message: "Demasiadas solicitudes, intenta más tarde" },
    },
  });
}

/**
 * Adapts ioredis `call` to the `sendCommand(...args)` signature rate-limit-redis expects.
 *
 * rate-limit-redis preloads its Lua scripts (SCRIPT LOAD) in its constructor and does not handle
 * a failed preload, so with Redis down at boot the rejection would be unhandled and crash the
 * process. A failed SCRIPT call resolves to an empty sha instead: the next EVALSHA then fails,
 * the store reloads the script, and the error reaches FailoverStore, which falls back to memory.
 */
const redisCommand =
  (redis: Pick<Redis, "call">) =>
  async (...args: string[]): Promise<RedisReply> => {
    const [command = "", ...rest] = args;
    try {
      return (await redis.call(command, ...rest)) as RedisReply;
    } catch (err) {
      if (command === "SCRIPT") return "";
      throw err;
    }
  };
