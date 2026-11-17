import request from "supertest";
import { Prisma } from "@prisma/client";
import { bearer, buildApp } from "./helpers";

const PARTIDO = "66666666-6666-4666-8666-666666666666";
const JUGADOR = "77777777-7777-4777-8777-777777777777";
const EQUIPO = "88888888-8888-4888-8888-888888888888";
const ESTAD = "99999999-9999-4999-8999-999999999999";
const OTRO_JUGADOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const partidoDe = (deporte: "BASQUETBOL" | "FUTBOL" | "AMERICANO") => ({
  id: PARTIDO,
  liga: { deporte },
});

const estadistica = (over: Record<string, unknown> = {}) => ({
  id: ESTAD,
  partidoId: PARTIDO,
  jugadorId: JUGADOR,
  equipoId: EQUIPO,
  deporte: "BASQUETBOL",
  minutos: 30,
  metricas: { puntos: 20, rebotes: 5, asistencias: 3 },
  creadoEn: new Date(),
  ...over,
});

const linea = (over: Record<string, unknown> = {}) => ({
  partidoId: PARTIDO,
  jugadorId: JUGADOR,
  equipoId: EQUIPO,
  minutos: 30,
  metricas: { puntos: 20, rebotes: 5, asistencias: 3 },
  ...over,
});

const p2002 = () =>
  new Prisma.PrismaClientKnownRequestError("dup", { code: "P2002", clientVersion: "5.22.0" });

describe("/api/estadisticas reads", () => {
  it("requires a token", async () => {
    const { app } = buildApp();
    expect((await request(app).get("/api/estadisticas")).status).toBe(401);
  });

  it("filters by ?jugadorId= and ?partidoId= with pagination", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.findMany.mockResolvedValue([estadistica()] as never);
    prisma.estadisticaJugadorPartido.count.mockResolvedValue(1);
    const res = await request(app)
      .get(`/api/estadisticas?jugadorId=${JUGADOR}&partidoId=${PARTIDO}&page=2&pageSize=10`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ total: 1, page: 2, pageSize: 10 });
    expect(prisma.estadisticaJugadorPartido.findMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { jugadorId: JUGADOR, partidoId: PARTIDO },
        skip: 10,
        take: 10,
      }),
    );
  });

  it("rejects a malformed ?jugadorId=", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .get("/api/estadisticas?jugadorId=abc")
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
  });

  it("GET /:id returns 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.findUnique.mockResolvedValue(null);
    const res = await request(app).get(`/api/estadisticas/${ESTAD}`).set("Authorization", bearer());
    expect(res.status).toBe(404);
  });
});

describe("/api/estadisticas writes", () => {
  it("POST is ADMIN only", async () => {
    const { app, prisma } = buildApp();
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer())
      .send(linea());
    expect(res.status).toBe(403);
    expect(prisma.estadisticaJugadorPartido.create).not.toHaveBeenCalled();
  });

  it("POST takes the sport from the partido's liga and validates metricas", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(partidoDe("BASQUETBOL") as never);
    prisma.estadisticaJugadorPartido.create.mockResolvedValue(estadistica() as never);
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send(linea({ deporte: "FUTBOL" }));
    expect(res.status).toBe(201);
    expect(prisma.estadisticaJugadorPartido.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ deporte: "BASQUETBOL", partidoId: PARTIDO }),
      }),
    );
  });

  it("POST rejects metricas that break the sport's schema with 400 and the path", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(partidoDe("FUTBOL") as never);
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send(linea({ metricas: { goles: -1, asistencias: 0 } }));
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_ERROR");
    expect(res.body.error.details).toEqual([expect.objectContaining({ path: "metricas.goles" })]);
    expect(prisma.estadisticaJugadorPartido.create).not.toHaveBeenCalled();
  });

  it("POST rejects a body without the required ids", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send({ metricas: {} });
    expect(res.status).toBe(400);
  });

  it("POST returns 404 when the partido does not exist", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send(linea());
    expect(res.status).toBe(404);
  });

  it("POST maps a duplicate (partido, jugador) to 409", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(partidoDe("BASQUETBOL") as never);
    prisma.estadisticaJugadorPartido.create.mockRejectedValue(p2002());
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send(linea());
    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe("DUPLICATE");
  });

  it("POST maps a missing jugador or equipo (FK) to 400 INVALID_REFERENCE", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(partidoDe("BASQUETBOL") as never);
    prisma.estadisticaJugadorPartido.create.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError("fk", {
        code: "P2003",
        clientVersion: "5.22.0",
      }),
    );
    const res = await request(app)
      .post("/api/estadisticas")
      .set("Authorization", bearer("ADMIN"))
      .send(linea({ jugadorId: OTRO_JUGADOR }));
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("INVALID_REFERENCE");
  });

  it("PUT re-validates the merged metricas against the partido's sport", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.findUnique.mockResolvedValue(estadistica() as never);
    prisma.partido.findUnique.mockResolvedValue(partidoDe("FUTBOL") as never);
    // Stored metrics are basketball-shaped; under FUTBOL they are not valid.
    const res = await request(app)
      .put(`/api/estadisticas/${ESTAD}`)
      .set("Authorization", bearer("ADMIN"))
      .send({ partidoId: PARTIDO });
    expect(res.status).toBe(400);
    expect(prisma.estadisticaJugadorPartido.update).not.toHaveBeenCalled();
  });

  it("PUT with only minutos keeps valid metricas and updates", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.findUnique.mockResolvedValue(estadistica() as never);
    prisma.partido.findUnique.mockResolvedValue(partidoDe("BASQUETBOL") as never);
    prisma.estadisticaJugadorPartido.update.mockResolvedValue(
      estadistica({ minutos: 35 }) as never,
    );
    const res = await request(app)
      .put(`/api/estadisticas/${ESTAD}`)
      .set("Authorization", bearer("ADMIN"))
      .send({ minutos: 35 });
    expect(res.status).toBe(200);
    expect(prisma.estadisticaJugadorPartido.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: ESTAD },
        data: expect.objectContaining({ minutos: 35, deporte: "BASQUETBOL" }),
      }),
    );
  });

  it("PUT returns 404 for a missing row and 403 for non-admins", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.findUnique.mockResolvedValue(null);
    expect(
      (
        await request(app)
          .put(`/api/estadisticas/${ESTAD}`)
          .set("Authorization", bearer("ADMIN"))
          .send({ minutos: 1 })
      ).status,
    ).toBe(404);
    expect(
      (
        await request(app)
          .put(`/api/estadisticas/${ESTAD}`)
          .set("Authorization", bearer())
          .send({ minutos: 1 })
      ).status,
    ).toBe(403);
  });

  it("DELETE is ADMIN only and returns 204", async () => {
    const { app, prisma } = buildApp();
    prisma.estadisticaJugadorPartido.delete.mockResolvedValue(estadistica() as never);
    expect(
      (await request(app).delete(`/api/estadisticas/${ESTAD}`).set("Authorization", bearer()))
        .status,
    ).toBe(403);
    const ok = await request(app)
      .delete(`/api/estadisticas/${ESTAD}`)
      .set("Authorization", bearer("ADMIN"));
    expect(ok.status).toBe(204);
  });
});

describe("POST /api/estadisticas/lote", () => {
  it("is ADMIN only", async () => {
    const { app, prisma } = buildApp();
    const res = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer())
      .send([linea()]);
    expect(res.status).toBe(403);
    expect(prisma.$transaction).not.toHaveBeenCalled();
  });

  it("upserts every valid line in one transaction, each with its sport", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findMany.mockResolvedValue([
      { id: PARTIDO, liga: { deporte: "BASQUETBOL" } },
      { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", liga: { deporte: "FUTBOL" } },
    ] as never);
    prisma.$transaction.mockImplementation((ops: unknown) => Promise.all(ops as never[]));
    prisma.estadisticaJugadorPartido.upsert.mockResolvedValue(estadistica() as never);

    const res = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer("ADMIN"))
      .send([
        linea(),
        linea({
          partidoId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          jugadorId: OTRO_JUGADOR,
          metricas: { goles: 1, asistencias: 0 },
        }),
      ]);

    expect(res.status).toBe(200);
    expect(res.body.procesadas).toBe(2);
    expect(prisma.$transaction).toHaveBeenCalledTimes(1);
    expect(prisma.estadisticaJugadorPartido.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { partidoId_jugadorId: { partidoId: PARTIDO, jugadorId: JUGADOR } },
        create: expect.objectContaining({ deporte: "BASQUETBOL" }),
      }),
    );
    expect(prisma.estadisticaJugadorPartido.upsert).toHaveBeenLastCalledWith(
      expect.objectContaining({
        create: expect.objectContaining({ deporte: "FUTBOL", jugadorId: OTRO_JUGADOR }),
      }),
    );
  });

  it("rejects the whole batch with per-index errors when any line is invalid", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findMany.mockResolvedValue([
      { id: PARTIDO, liga: { deporte: "BASQUETBOL" } },
    ] as never);
    const res = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer("ADMIN"))
      .send([
        linea(),
        linea({ metricas: { puntos: -5, rebotes: 1, asistencias: 1 } }),
        linea({ jugadorId: undefined }),
        linea({ partidoId: "cccccccc-cccc-4ccc-8ccc-cccccccccccc" }),
      ]);
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_ERROR");
    const detalles = res.body.error.details as Array<{ index: number; path: string }>;
    expect(detalles.map((d) => d.index)).toEqual([1, 2, 3]);
    expect(detalles[0]).toMatchObject({ index: 1, path: "metricas.puntos" });
    expect(detalles[2]).toMatchObject({ index: 3, path: "partidoId" });
    expect(prisma.$transaction).not.toHaveBeenCalled();
  });

  it("rejects an empty array and more than 500 lines", async () => {
    const { app } = buildApp();
    const empty = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer("ADMIN"))
      .send([]);
    expect(empty.status).toBe(400);
    const tooMany = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer("ADMIN"))
      .send(Array.from({ length: 501 }, () => linea()));
    expect(tooMany.status).toBe(400);
  });

  it("reports a rolled-back transaction as a 400 mapped error, not a partial write", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findMany.mockResolvedValue([
      { id: PARTIDO, liga: { deporte: "BASQUETBOL" } },
    ] as never);
    prisma.$transaction.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError("fk", { code: "P2003", clientVersion: "5.22.0" }),
    );
    const res = await request(app)
      .post("/api/estadisticas/lote")
      .set("Authorization", bearer("ADMIN"))
      .send([linea()]);
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("INVALID_REFERENCE");
  });
});
