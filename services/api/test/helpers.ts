import type { PrismaClient } from "@prisma/client";
import { mockDeep, type DeepMockProxy } from "jest-mock-extended";
import pino from "pino";
import type Redis from "ioredis";
import RedisMock from "ioredis-mock";
import { createApp, type AppDeps } from "../src/app";
import { defaultSchemasDir } from "../src/config";
import { createTokenService, type Rol } from "../src/lib/auth";
import { createMetricasValidator } from "../src/lib/metricas";
import { createMetrics } from "../src/lib/metrics";
import type { RedisHandle } from "../src/lib/redis";

export const tokens = createTokenService({
  accessSecret: "test-access-secret-0123456789",
  refreshSecret: "test-refresh-secret-0123456789",
  accessTtl: "5m",
  refreshTtl: "1h",
});

export function buildApp(overrides: Partial<AppDeps> = {}) {
  const prisma = mockDeep<PrismaClient>() as DeepMockProxy<PrismaClient>;
  const metrics = overrides.metrics ?? createMetrics();
  const app = createApp({
    prisma: prisma as unknown as PrismaClient,
    tokens,
    metrics,
    metricas: createMetricasValidator(defaultSchemasDir),
    logger: pino({ level: "silent" }),
    ...overrides,
  });
  return { app, prisma, metrics };
}

export const USER_ID = "11111111-1111-4111-8111-111111111111";
export const ADMIN_ID = "22222222-2222-4222-8222-222222222222";

export const bearer = (rol: Rol = "USUARIO", sub = rol === "ADMIN" ? ADMIN_ID : USER_ID) =>
  `Bearer ${tokens.signAccess({ sub, rol })}`;

/**
 * ioredis-mock covering GET/SET/INCR/TTL. It has no Lua support, so `call` emulates the two
 * scripts rate-limit-redis uses (SCRIPT LOAD and EVALSHA of its increment script).
 */
let mockHosts = 0;

/** Each mock gets its own host: ioredis-mock otherwise shares data between instances. */
export function mockRedis(): Redis {
  const counters = new Map<string, { hits: number; expiresAt: number }>();
  const call = async (command: string, ...args: unknown[]): Promise<unknown> => {
    if (command === "SCRIPT") return "sha";
    if (command === "EVALSHA") {
      const [, , key, resetOnChange, windowMs] = args.map(String);
      const now = Date.now();
      const window = Number(windowMs);
      const entry = counters.get(key!);
      if (!entry || entry.expiresAt <= now) {
        counters.set(key!, { hits: 1, expiresAt: now + window });
        return [1, window];
      }
      entry.hits += 1;
      if (resetOnChange === "1") entry.expiresAt = now + window;
      return [entry.hits, entry.expiresAt - now];
    }
    throw new Error(`unsupported command ${command}`);
  };
  return Object.assign(new RedisMock({ host: `mock-${++mockHosts}` }), {
    call,
  }) as unknown as Redis;
}

export const redisHandle = (client: Redis): RedisHandle => ({
  client,
  ping: async () => undefined,
  close: async () => undefined,
});
