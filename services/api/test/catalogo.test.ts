import request from "supertest";
import { Prisma } from "@prisma/client";
import { bearer, buildApp } from "./helpers";

const LIGA_ID = "33333333-3333-4333-8333-333333333333";
const A = "44444444-4444-4444-8444-444444444444";
const B = "55555555-5555-4555-8555-555555555555";
const PARTIDO_ID = "66666666-6666-4666-8666-666666666666";

const liga = {
  id: LIGA_ID,
  nombre: "Liga MX",
  deporte: "FUTBOL" as const,
  pais: "México",
  temporada: "2026",
  proveedor: "api-sports",
  proveedorLigaId: "262",
  activa: true,
  creadoEn: new Date(),
};

const partido = (over: Partial<Record<string, unknown>> = {}) => ({
  id: PARTIDO_ID,
  ligaId: LIGA_ID,
  localId: A,
  visitaId: B,
  fecha: new Date("2026-11-14T02:00:00Z"),
  jornada: 17,
  temporada: "2026",
  estatus: "FINALIZADO",
  marcadorLocal: 2,
  marcadorVisita: 1,
  proveedorId: "1",
  ...over,
});

describe("/api/ligas", () => {
  it("requires a token", async () => {
    const { app } = buildApp();
    expect((await request(app).get("/api/ligas")).status).toBe(401);
  });

  it("lists with ?deporte= and pagination", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.findMany.mockResolvedValue([liga]);
    prisma.liga.count.mockResolvedValue(1);
    const res = await request(app)
      .get("/api/ligas?deporte=FUTBOL&page=2&pageSize=5")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.total).toBe(1);
    expect(prisma.liga.findMany).toHaveBeenCalledWith(
      expect.objectContaining({ where: { deporte: "FUTBOL" }, skip: 5, take: 5 }),
    );
  });

  it("rejects an unknown deporte", async () => {
    const { app } = buildApp();
    const res = await request(app).get("/api/ligas?deporte=TENIS").set("Authorization", bearer());
    expect(res.status).toBe(400);
  });

  it("only ADMIN can create; body is validated", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.create.mockResolvedValue(liga);
    const body = {
      nombre: "Liga MX",
      deporte: "FUTBOL",
      temporada: "2026",
      proveedorLigaId: "262",
    };
    expect(
      (await request(app).post("/api/ligas").set("Authorization", bearer()).send(body)).status,
    ).toBe(403);
    const ok = await request(app)
      .post("/api/ligas")
      .set("Authorization", bearer("ADMIN"))
      .send(body);
    expect(ok.status).toBe(201);
    const bad = await request(app)
      .post("/api/ligas")
      .set("Authorization", bearer("ADMIN"))
      .send({ nombre: "x" });
    expect(bad.status).toBe(400);
  });

  it("GET /:id is 404 when missing and 400 for a non-uuid id", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).get(`/api/ligas/${LIGA_ID}`).set("Authorization", bearer())).status,
    ).toBe(404);
    expect((await request(app).get("/api/ligas/abc").set("Authorization", bearer())).status).toBe(
      400,
    );
  });

  it("PUT and DELETE map Prisma P2025 to 404", async () => {
    const { app, prisma } = buildApp();
    const p2025 = new Prisma.PrismaClientKnownRequestError("not found", {
      code: "P2025",
      clientVersion: "5.22.0",
    });
    prisma.liga.update.mockRejectedValue(p2025);
    prisma.liga.delete.mockResolvedValue(liga);
    const put = await request(app)
      .put(`/api/ligas/${LIGA_ID}`)
      .set("Authorization", bearer("ADMIN"))
      .send({ activa: false });
    expect(put.status).toBe(404);
    const del = await request(app)
      .delete(`/api/ligas/${LIGA_ID}`)
      .set("Authorization", bearer("ADMIN"));
    expect(del.status).toBe(204);
  });

  it("maps a unique-constraint violation to 409", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.create.mockRejectedValue(
      new Prisma.PrismaClientKnownRequestError("dup", { code: "P2002", clientVersion: "5.22.0" }),
    );
    const res = await request(app)
      .post("/api/ligas")
      .set("Authorization", bearer("ADMIN"))
      .send({ nombre: "Liga MX", deporte: "FUTBOL", temporada: "2026", proveedorLigaId: "262" });
    expect(res.status).toBe(409);
  });

  it("GET /:id/posiciones builds the table from finished games", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.findUnique.mockResolvedValue({
      ...liga,
      equipos: [
        { id: A, nombre: "América", abreviatura: "AME" },
        { id: B, nombre: "Chivas", abreviatura: "GDL" },
      ],
    } as never);
    prisma.partido.findMany.mockResolvedValue([partido()] as never);
    const res = await request(app)
      .get(`/api/ligas/${LIGA_ID}/posiciones`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.posiciones[0]).toMatchObject({ posicion: 1, equipoId: A, puntos: 3 });
    expect(res.body.posiciones[0].equipo.abreviatura).toBe("AME");
  });

  it("GET /:id/posiciones is 404 for an unknown liga", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/ligas/${LIGA_ID}/posiciones`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("GET /:id/calendario lists games by date", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findMany.mockResolvedValue([partido({ estatus: "PROGRAMADO" })] as never);
    const res = await request(app)
      .get(`/api/ligas/${LIGA_ID}/calendario`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.partidos).toHaveLength(1);
  });
});

describe("/api/equipos", () => {
  it("GET /:id/forma", async () => {
    const { app, prisma } = buildApp();
    prisma.equipo.findUnique.mockResolvedValue({ id: A } as never);
    prisma.partido.findMany.mockResolvedValue([partido(), partido({ marcadorLocal: 0 })] as never);
    const res = await request(app).get(`/api/equipos/${A}/forma`).set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.forma).toBe("PG");
  });

  it("GET /:id/forma is 404 for an unknown team", async () => {
    const { app, prisma } = buildApp();
    prisma.equipo.findUnique.mockResolvedValue(null);
    const res = await request(app).get(`/api/equipos/${A}/forma`).set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("lists equipos", async () => {
    const { app, prisma } = buildApp();
    prisma.equipo.findMany.mockResolvedValue([]);
    prisma.equipo.count.mockResolvedValue(0);
    const res = await request(app).get("/api/equipos").set("Authorization", bearer());
    expect(res.status).toBe(200);
  });
});

describe("/api/jugadores", () => {
  it("filters by ?q= (case-insensitive) and ?deporte=", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findMany.mockResolvedValue([]);
    prisma.jugador.count.mockResolvedValue(0);
    const res = await request(app)
      .get("/api/jugadores?q=curry&deporte=BASQUETBOL")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(prisma.jugador.findMany.mock.calls[0]![0]!.where).toEqual({
      deporte: "BASQUETBOL",
      nombre: { contains: "curry", mode: "insensitive" },
    });
  });
});

describe("/api/partidos", () => {
  it("filters ?fecha= as a UTC day and ?jornada=", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findMany.mockResolvedValue([]);
    prisma.partido.count.mockResolvedValue(0);
    const res = await request(app)
      .get("/api/partidos?fecha=2026-11-14&jornada=17")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(prisma.partido.findMany.mock.calls[0]![0]!.where).toEqual({
      jornada: 17,
      fecha: { gte: new Date("2026-11-14T00:00:00Z"), lt: new Date("2026-11-15T00:00:00Z") },
    });
  });

  it("GET /:id/boxscore splits lines by team", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue({
      ...partido(),
      local: { id: A },
      visita: { id: B },
      estadisticas: [
        { equipoId: A, metricas: { goles: 1 } },
        { equipoId: B, metricas: { goles: 1 } },
        { equipoId: A, metricas: { goles: 1 } },
      ],
    } as never);
    const res = await request(app)
      .get(`/api/partidos/${PARTIDO_ID}/boxscore`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.local).toHaveLength(2);
    expect(res.body.visita).toHaveLength(1);
    expect(res.body.partido).not.toHaveProperty("estadisticas");
  });

  it("GET /:id/boxscore is 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/partidos/${PARTIDO_ID}/boxscore`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("GET /:id returns the game", async () => {
    const { app, prisma } = buildApp();
    prisma.partido.findUnique.mockResolvedValue(partido() as never);
    const res = await request(app)
      .get(`/api/partidos/${PARTIDO_ID}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
  });
});

describe("unexpected errors", () => {
  it("are 500 without leaking details", async () => {
    const { app, prisma } = buildApp();
    prisma.liga.findMany.mockRejectedValue(new Error("connection reset by peer"));
    prisma.liga.count.mockResolvedValue(0);
    const res = await request(app).get("/api/ligas").set("Authorization", bearer());
    expect(res.status).toBe(500);
    expect(JSON.stringify(res.body)).not.toContain("connection reset");
  });
});
