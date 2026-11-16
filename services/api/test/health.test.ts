import request from "supertest";
import { buildApp } from "./helpers";

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
