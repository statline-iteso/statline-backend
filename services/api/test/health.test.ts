import request from "supertest";
import { buildApp, mockRedis } from "./helpers";

describe("health endpoints", () => {
  it("GET /healthz answers ok without touching the database", async () => {
    const { app, prisma } = buildApp();
    const res = await request(app).get("/healthz");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: "ok" });
    expect(prisma.$queryRaw).not.toHaveBeenCalled();
  });

  it("GET /readyz is 200 when the database answers", async () => {
    const { app, prisma } = buildApp();
    prisma.$queryRaw.mockResolvedValue([{ "?column?": 1 }] as never);
    const res = await request(app).get("/readyz");
    expect(res.status).toBe(200);
    expect(res.body.checks.db).toBe("ok");
  });

  it("GET /readyz is 503 when the database is down", async () => {
    const { app, prisma } = buildApp();
    prisma.$queryRaw.mockRejectedValue(new Error("ECONNREFUSED"));
    const res = await request(app).get("/readyz");
    expect(res.status).toBe(503);
    expect(res.body.checks.db).toBe("down");
  });

  it("GET /metrics exposes Prometheus metrics", async () => {
    const { app } = buildApp();
    await request(app).get("/healthz");
    const res = await request(app).get("/metrics");
    expect(res.status).toBe(200);
    expect(res.text).toContain("statline_http_requests_total");
  });

  it("unknown routes are 404 with the error shape", async () => {
    const { app } = buildApp();
    const res = await request(app).get("/nope");
    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe("NOT_FOUND");
  });
});

describe("GET /readyz with Redis", () => {
  const redis = (ping: () => Promise<void>) => ({
    client: mockRedis(),
    ping,
    close: async () => undefined,
  });

  it("is 200 when the database and Redis both answer", async () => {
    const { app, prisma } = buildApp({ redis: redis(async () => undefined) });
    prisma.$queryRaw.mockResolvedValue([] as never);
    const res = await request(app).get("/readyz");
    expect(res.status).toBe(200);
    expect(res.body.checks).toEqual({ db: "ok", redis: "ok" });
  });

  it("is 503 and names redis when Redis fails", async () => {
    const { app, prisma } = buildApp({
      redis: redis(() => Promise.reject(new Error("ECONNREFUSED"))),
    });
    prisma.$queryRaw.mockResolvedValue([] as never);
    const res = await request(app).get("/readyz");
    expect(res.status).toBe(503);
    expect(res.body.checks).toEqual({ db: "ok", redis: "down" });
  });

  it("reports both dependencies when both fail", async () => {
    const { app, prisma } = buildApp({
      redis: redis(() => Promise.reject(new Error("down"))),
    });
    prisma.$queryRaw.mockRejectedValue(new Error("down"));
    const res = await request(app).get("/readyz");
    expect(res.status).toBe(503);
    expect(res.body.checks).toEqual({ db: "down", redis: "down" });
  });
});
