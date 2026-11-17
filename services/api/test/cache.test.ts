import request from "supertest";
import type Redis from "ioredis";
import pino from "pino";
import { createMetrics } from "../src/lib/metrics";
import { bearer, buildApp, mockRedis, redisHandle } from "./helpers";

const LIGA_ID = "33333333-3333-4333-8333-333333333333";
const liga = {
  id: LIGA_ID,
  nombre: "Liga MX",
  deporte: "FUTBOL",
  pais: "México",
  temporada: "2026",
  proveedor: "api-sports",
  proveedorLigaId: "262",
  activa: true,
  creadoEn: new Date("2026-01-01T00:00:00Z"),
};

const cacheHeader = (res: request.Response) => res.headers["x-cache"];

describe("catalog cache", () => {
  it("serves the second GET from Redis and records hit and miss", async () => {
    const redis = mockRedis();
    const { app, prisma, metrics } = buildApp({ redis: redisHandle(redis), cacheTtlS: 60 });
    prisma.liga.findMany.mockResolvedValue([liga] as never);
    prisma.liga.count.mockResolvedValue(1);

    const first = await request(app).get("/api/ligas").set("Authorization", bearer());
    const second = await request(app).get("/api/ligas").set("Authorization", bearer());

    expect(first.status).toBe(200);
    expect(cacheHeader(first)).toBe("MISS");
    expect(cacheHeader(second)).toBe("HIT");
    expect(second.body).toEqual(first.body);
    expect(prisma.liga.findMany).toHaveBeenCalledTimes(1);

    const counts = await metrics.registry.getSingleMetricAsString("statline_cache_requests_total");
    expect(counts).toContain('result="hit"');
    expect(counts).toContain('result="miss"');
  });

  it("keys entries by method and original URL, with the configured TTL", async () => {
    const redis = mockRedis();
    const { app, prisma } = buildApp({ redis: redisHandle(redis), cacheTtlS: 42 });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);

    await request(app).get("/api/ligas?deporte=FUTBOL").set("Authorization", bearer());
    await request(app).get("/api/ligas?deporte=BASQUETBOL").set("Authorization", bearer());

    expect(prisma.liga.findMany).toHaveBeenCalledTimes(2);
    const keys = (await redis.keys("statline:cache:catalogo:*")) as string[];
    expect(keys.filter((k) => k.includes(":GET:/api/ligas?deporte="))).toHaveLength(2);
    const ttl = await redis.ttl(keys.find((k) => k.endsWith("FUTBOL"))!);
    expect(ttl).toBeGreaterThan(0);
    expect(ttl).toBeLessThanOrEqual(42);
  });

  it("invalidates cached catalog reads after a successful write", async () => {
    const redis = mockRedis();
    const { app, prisma } = buildApp({ redis: redisHandle(redis) });
    prisma.liga.findMany.mockResolvedValue([liga] as never);
    prisma.liga.count.mockResolvedValue(1);
    prisma.liga.create.mockResolvedValue(liga as never);

    await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(cacheHeader(await request(app).get("/api/ligas").set("Authorization", bearer()))).toBe(
      "HIT",
    );

    const write = await request(app)
      .post("/api/ligas")
      .set("Authorization", bearer("ADMIN"))
      .send({ nombre: "Liga MX", deporte: "FUTBOL", temporada: "2026", proveedorLigaId: "262" });
    expect(write.status).toBe(201);

    const after = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(cacheHeader(after)).toBe("MISS");
    expect(prisma.liga.findMany).toHaveBeenCalledTimes(2);
  });

  it("does not invalidate on a rejected write", async () => {
    const redis = mockRedis();
    const { app, prisma } = buildApp({ redis: redisHandle(redis) });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);

    await request(app).get("/api/ligas").set("Authorization", bearer());
    const denied = await request(app).post("/api/ligas").set("Authorization", bearer()).send({});
    expect(denied.status).toBe(403);

    expect(cacheHeader(await request(app).get("/api/ligas").set("Authorization", bearer()))).toBe(
      "HIT",
    );
  });

  it("does not cache error responses", async () => {
    const redis = mockRedis();
    const { app, prisma } = buildApp({ redis: redisHandle(redis) });
    prisma.liga.findUnique.mockResolvedValue(null);
    const id = "44444444-4444-4444-8444-444444444444";

    await request(app).get(`/api/ligas/${id}`).set("Authorization", bearer());
    const again = await request(app).get(`/api/ligas/${id}`).set("Authorization", bearer());
    expect(again.status).toBe(404);
    expect(cacheHeader(again)).toBe("MISS");
    expect(prisma.liga.findUnique).toHaveBeenCalledTimes(2);
  });

  it("bypasses the cache when Redis fails and never fails the request", async () => {
    const broken = {
      get: jest.fn().mockRejectedValue(new Error("Connection is closed.")),
      set: jest.fn().mockRejectedValue(new Error("Connection is closed.")),
      incr: jest.fn().mockRejectedValue(new Error("Connection is closed.")),
    } as unknown as Redis;
    const { app, prisma, metrics } = buildApp({ redis: redisHandle(broken) });
    prisma.liga.findMany.mockResolvedValue([liga] as never);
    prisma.liga.count.mockResolvedValue(1);

    const read = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(read.status).toBe(200);
    expect(prisma.liga.findMany).toHaveBeenCalledTimes(1);

    const write = await request(app)
      .post("/api/ligas")
      .set("Authorization", bearer("ADMIN"))
      .send({ nombre: "Liga MX", deporte: "FUTBOL", temporada: "2026", proveedorLigaId: "262" });
    expect(write.status).toBe(201);
    const text = await metrics.registry.getSingleMetricAsString("statline_cache_requests_total");
    expect(text).toContain('result="bypass"');
  });

  it("bypasses every request when Redis is not configured", async () => {
    const { app, prisma, metrics } = buildApp({ cacheTtlS: 60 });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);
    const res = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(cacheHeader(res)).toBeUndefined();
    const text = await metrics.registry.getSingleMetricAsString("statline_cache_requests_total");
    expect(text).toContain('result="bypass"');
  });

  it("keeps working when only the store write fails", async () => {
    const redis = mockRedis();
    const failing = Object.assign(redis, {
      set: jest.fn().mockRejectedValue(new Error("boom")),
    });
    const { app, prisma } = buildApp({
      redis: redisHandle(failing as unknown as Redis),
      logger: pino({ level: "silent" }),
    });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);
    const res = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(res.status).toBe(200);
  });

  it("times out slow Redis calls and bypasses", async () => {
    const hanging = {
      get: () => new Promise(() => undefined),
      set: () => new Promise(() => undefined),
      incr: () => new Promise(() => undefined),
    } as unknown as Redis;
    const { app, prisma } = buildApp({ redis: redisHandle(hanging) });
    prisma.liga.findMany.mockResolvedValue([] as never);
    prisma.liga.count.mockResolvedValue(0);
    const res = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(prisma.liga.findMany).toHaveBeenCalledTimes(1);
  }, 5000);

  it("createMetrics exposes the cache counter", () => {
    expect(createMetrics().cacheRequests).toBeDefined();
  });
});
