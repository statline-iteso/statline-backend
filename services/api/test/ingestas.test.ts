import request from "supertest";
import { Prisma, type EjecucionIngesta } from "@prisma/client";
import { bearer, buildApp } from "./helpers";
import { crearLanzadorDeshabilitado, type LanzadorIngesta } from "../src/lib/ingesta-lanzador";
import { buildAppWithLanzador } from "./ingestas-helpers";

const INGESTA_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const ejecucion: EjecucionIngesta = {
  id: INGESTA_ID,
  deporte: "BASQUETBOL",
  proveedor: "api-sports",
  estatus: "EXITOSA",
  iniciadaEn: new Date("2026-11-16T08:00:00Z"),
  finalizadaEn: new Date("2026-11-16T08:05:00Z"),
  registrosProcesados: 12,
  peticionesUsadas: 3,
  error: null,
};

describe("/api/ingestas", () => {
  it("requires a token and ADMIN for every route", async () => {
    const { app, prisma } = buildApp();
    expect((await request(app).get("/api/ingestas")).status).toBe(401);
    expect((await request(app).get("/api/ingestas").set("Authorization", bearer())).status).toBe(
      403,
    );
    expect(
      (
        await request(app)
          .post("/api/ingestas/ejecutar")
          .set("Authorization", bearer())
          .send({ deporte: "FUTBOL" })
      ).status,
    ).toBe(403);
    expect(prisma.ejecucionIngesta.findMany).not.toHaveBeenCalled();
  });

  it("lists newest first with ?deporte= and ?estatus= filters", async () => {
    const { app, prisma } = buildApp();
    prisma.ejecucionIngesta.findMany.mockResolvedValue([ejecucion]);
    prisma.ejecucionIngesta.count.mockResolvedValue(1);
    const res = await request(app)
      .get("/api/ingestas?deporte=BASQUETBOL&estatus=EXITOSA&page=2&pageSize=10")
      .set("Authorization", bearer("ADMIN"));
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ total: 1, page: 2, pageSize: 10 });
    expect(prisma.ejecucionIngesta.findMany).toHaveBeenCalledWith({
      where: { deporte: "BASQUETBOL", estatus: "EXITOSA" },
      include: undefined,
      orderBy: { iniciadaEn: "desc" },
      skip: 10,
      take: 10,
    });
  });

  it("rejects an unknown estatus filter with 400", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .get("/api/ingestas?estatus=RARO")
      .set("Authorization", bearer("ADMIN"));
    expect(res.status).toBe(400);
  });

  it("GET /:id returns the run, 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.ejecucionIngesta.findUnique.mockResolvedValue(ejecucion);
    const ok = await request(app)
      .get(`/api/ingestas/${INGESTA_ID}`)
      .set("Authorization", bearer("ADMIN"));
    expect(ok.status).toBe(200);
    expect(ok.body.estatus).toBe("EXITOSA");

    prisma.ejecucionIngesta.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).get(`/api/ingestas/${INGESTA_ID}`).set("Authorization", bearer("ADMIN")))
        .status,
    ).toBe(404);
  });

  it("DELETE removes the audit record with 204 and maps P2025 to 404", async () => {
    const { app, prisma } = buildApp();
    prisma.ejecucionIngesta.delete.mockResolvedValue(ejecucion);
    expect(
      (
        await request(app)
          .delete(`/api/ingestas/${INGESTA_ID}`)
          .set("Authorization", bearer("ADMIN"))
      ).status,
    ).toBe(204);

    prisma.ejecucionIngesta.delete.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError("nf", { code: "P2025", clientVersion: "5.22.0" }),
    );
    expect(
      (
        await request(app)
          .delete(`/api/ingestas/${INGESTA_ID}`)
          .set("Authorization", bearer("ADMIN"))
      ).status,
    ).toBe(404);
  });

  it("has no create or update routes", async () => {
    const { app } = buildApp();
    expect(
      (
        await request(app)
          .post("/api/ingestas")
          .set("Authorization", bearer("ADMIN"))
          .send({ deporte: "FUTBOL" })
      ).status,
    ).toBe(404);
    expect(
      (
        await request(app)
          .put(`/api/ingestas/${INGESTA_ID}`)
          .set("Authorization", bearer("ADMIN"))
          .send({})
      ).status,
    ).toBe(404);
  });

  it("POST /ejecutar answers 503 NOT_CONFIGURED with the default launcher", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .post("/api/ingestas/ejecutar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "FUTBOL" });
    expect(res.status).toBe(503);
    expect(res.body.error.code).toBe("NOT_CONFIGURED");
  });

  it("POST /ejecutar validates deporte before launching", async () => {
    const lanzar = jest.fn();
    const lanzador: LanzadorIngesta = { lanzar };
    const { app } = buildAppWithLanzador(lanzador);
    const res = await request(app)
      .post("/api/ingestas/ejecutar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "TENIS" });
    expect(res.status).toBe(400);
    expect(lanzar).not.toHaveBeenCalled();
  });

  it("POST /ejecutar answers 202 with the job name when the launcher starts it", async () => {
    const lanzar = jest.fn().mockResolvedValue({ job: "ingesta-futbol-manual-1" });
    const { app } = buildAppWithLanzador({ lanzar });
    const res = await request(app)
      .post("/api/ingestas/ejecutar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "FUTBOL" });
    expect(res.status).toBe(202);
    expect(res.body).toEqual({ job: "ingesta-futbol-manual-1" });
    expect(lanzar).toHaveBeenCalledWith("FUTBOL");
  });

  it("the disabled launcher rejects with 503 NOT_CONFIGURED", async () => {
    await expect(crearLanzadorDeshabilitado().lanzar("FUTBOL")).rejects.toMatchObject({
      status: 503,
      code: "NOT_CONFIGURED",
    });
  });
});
