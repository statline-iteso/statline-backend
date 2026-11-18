import request from "supertest";
import type Redis from "ioredis";
import pino from "pino";
import { MemoryStore } from "express-rate-limit";
import { FailoverStore } from "../src/lib/rate-limit";
import { bearer, buildApp, mockRedis, redisHandle } from "./helpers";

const logger = pino({ level: "silent" });

describe("rate limiting", () => {
  it("answers 429 with the error shape once the global /api limit is exceeded", async () => {
    const { app, prisma } = buildApp({ rateLimits: { global: 2, login: 10 } });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);

    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(200);
    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(200);
    const limited = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(limited.status).toBe(429);
    expect(limited.body.error.code).toBe("RATE_LIMITED");
    expect(limited.headers["ratelimit-policy"]).toBeDefined();
  });

  it("limits POST /api/auth/login more strictly, per IP", async () => {
    const { app, prisma } = buildApp({ rateLimits: { global: 300, login: 1 } });
    prisma.usuario.findUnique.mockResolvedValue(null);
    const attempt = () =>
      request(app).post("/api/auth/login").send({ email: "a@b.co", password: "wrong-password" });

    expect((await attempt()).status).toBe(401);
    expect((await attempt()).status).toBe(429);
  });

  it("never rate limits probes or /metrics", async () => {
    const { app } = buildApp({ rateLimits: { global: 1, login: 1 } });
    for (let i = 0; i < 5; i++) {
      expect((await request(app).get("/healthz")).status).toBe(200);
      expect((await request(app).get("/metrics")).status).toBe(200);
    }
  });

  it("counts through Redis when it is configured", async () => {
    const redis = mockRedis();
    const spy = jest.spyOn(redis, "call");
    const { app, prisma } = buildApp({
      redis: redisHandle(redis),
      rateLimits: { global: 1, login: 10 },
    });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);

    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(200);
    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(429);
    const commands = spy.mock.calls;
    expect(commands.some(([cmd]) => cmd === "EVALSHA")).toBe(true);
    expect(commands.some(([, , , key]) => String(key).startsWith("statline:rl:global:"))).toBe(
      true,
    );
  });

  it("falls back to memory counting when Redis fails", async () => {
    const broken = {
      call: jest.fn().mockRejectedValue(new Error("Stream isn't writeable")),
    } as unknown as Redis;
    const { app, prisma } = buildApp({
      redis: redisHandle(broken),
      rateLimits: { global: 1, login: 10 },
    });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);

    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(200);
    expect((await request(app).get("/api/ligas").set("Authorization", bearer())).status).toBe(429);
    expect(broken.call).toHaveBeenCalled();
  });

  it("FailoverStore uses the fallback when primary decrement and resetKey fail", async () => {
    const primary = new MemoryStore();
    const fallback = new MemoryStore();
    const failing = Object.assign(new MemoryStore(), {
      decrement: jest.fn().mockRejectedValue(new Error("down")),
      resetKey: jest.fn().mockRejectedValue(new Error("down")),
    });
    const store = new FailoverStore(failing, fallback, "p:", logger);
    expect(store.prefix).toBe("p:");
    expect(store.localKeys).toBe(false);
    store.init({ windowMs: 60_000 } as never);
    await expect(store.increment("k")).resolves.toMatchObject({ totalHits: 1 });
    await expect(store.decrement("k")).resolves.toBeUndefined();
    await expect(store.resetKey("k")).resolves.toBeUndefined();
    expect(failing.decrement).toHaveBeenCalled();
    expect(failing.resetKey).toHaveBeenCalled();
    void primary;
  });
});
