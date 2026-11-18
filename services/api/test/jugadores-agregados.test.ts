import request from "supertest";
import { bearer, buildApp } from "./helpers";

const JUGADOR = "77777777-7777-4777-8777-777777777777";
const OTRO = "88888888-8888-4888-8888-888888888888";
const TERCERO = "99999999-9999-4999-8999-999999999999";
const PARTIDO = "66666666-6666-4666-8666-666666666666";

const ref = (id: string, deporte: "BASQUETBOL" | "AMERICANO" | "FUTBOL" = "BASQUETBOL") => ({
  id,
  nombre: `Jugador ${id.slice(0, 4)}`,
  deporte,
  posicion: "G",
});

/** SQL text and bound values of the nth $queryRaw call (Prisma.sql objects or tagged templates). */
const sqlDe = (call: unknown[]) => {
  const [first, ...rest] = call;
  if (typeof first === "object" && first !== null && "sql" in first && "values" in first) {
    const sql = first as { sql: string; values: unknown[] };
    return { text: sql.sql, values: sql.values };
  }
  return { text: (first as TemplateStringsArray).join("?"), values: rest };
};

describe("GET /api/jugadores/:id/promedios", () => {
  it("returns games, average minutes and one average per numeric metric", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    prisma.$queryRaw
      .mockResolvedValueOnce([{ partidos: 3, minutosPromedio: 30.5 }] as never)
      .mockResolvedValueOnce([{ metrica: "puntos", promedio: 20 }] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/promedios`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      jugador: ref(JUGADOR),
      ultimos: null,
      partidos: 3,
      minutosPromedio: 30.5,
      promedios: expect.objectContaining({ puntos: 20, rebotes: null }),
    });
    expect(res.body.promedios).not.toHaveProperty("nombre");
  });

  it("restricts to the last N games with ?ultimos= and binds N as a parameter", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    prisma.$queryRaw
      .mockResolvedValueOnce([{ partidos: 5, minutosPromedio: null }] as never)
      .mockResolvedValueOnce([] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/promedios?ultimos=5`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.ultimos).toBe(5);
    const { text, values } = sqlDe(prisma.$queryRaw.mock.calls[0]!);
    expect(text).toContain("LIMIT");
    expect(values).toContain(5);
    expect(values).toContain(JUGADOR);
    expect(text).not.toContain(JUGADOR);
  });

  it("returns zero games and empty averages without a metrics query", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    prisma.$queryRaw.mockResolvedValueOnce([{ partidos: 0, minutosPromedio: null }] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/promedios`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ partidos: 0, minutosPromedio: null, promedios: {} });
    expect(prisma.$queryRaw).toHaveBeenCalledTimes(1);
  });

  it("returns 400 for an invalid ?ultimos=", async () => {
    const { app, prisma } = buildApp();
    for (const q of ["0", "abc", "501", ""]) {
      const res = await request(app)
        .get(`/api/jugadores/${JUGADOR}/promedios?ultimos=${q}`)
        .set("Authorization", bearer());
      expect(res.status).toBe(400);
    }
    expect(prisma.jugador.findUnique).not.toHaveBeenCalled();
  });

  it("returns 400 for a non-uuid id and 404 when the player is missing", async () => {
    const { app, prisma } = buildApp();
    expect(
      (await request(app).get("/api/jugadores/abc/promedios").set("Authorization", bearer()))
        .status,
    ).toBe(400);
    prisma.jugador.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/promedios`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe("NOT_FOUND");
  });

  it("requires a token", async () => {
    const { app } = buildApp();
    expect((await request(app).get(`/api/jugadores/${JUGADOR}/promedios`)).status).toBe(401);
  });

  it("uses NFL dotted paths for grouped metrics", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR, "AMERICANO") as never);
    prisma.$queryRaw
      .mockResolvedValueOnce([{ partidos: 1, minutosPromedio: null }] as never)
      .mockResolvedValueOnce([{ metrica: "pase.yardas", promedio: 250 }] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/promedios`)
      .set("Authorization", bearer());
    expect(res.body.promedios["pase.yardas"]).toBe(250);
  });
});

describe("GET /api/jugadores/:id/tendencia", () => {
  it("returns the per-game series oldest first", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    prisma.$queryRaw.mockResolvedValueOnce([
      { partidoId: PARTIDO, fecha: new Date("2026-11-14T02:00:00Z"), valor: 30 },
      { partidoId: OTRO, fecha: new Date("2026-11-12T02:00:00Z"), valor: 12 },
    ] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=puntos&n=2`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      jugadorId: JUGADOR,
      metrica: "puntos",
      n: 2,
      serie: [
        { partidoId: OTRO, fecha: "2026-11-12T02:00:00.000Z", valor: 12 },
        { partidoId: PARTIDO, fecha: "2026-11-14T02:00:00.000Z", valor: 30 },
      ],
    });
    const { values } = sqlDe(prisma.$queryRaw.mock.calls[0]!);
    expect(values).toEqual(expect.arrayContaining(["puntos", JUGADOR, 2]));
  });

  it("defaults n to 10", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    prisma.$queryRaw.mockResolvedValueOnce([] as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=rebotes`)
      .set("Authorization", bearer());
    expect(res.body.n).toBe(10);
  });

  it("returns 400 for an unknown metric and lists the valid ones", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR) as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=asesinatos`)
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_ERROR");
    expect(res.body.error.details.metricasValidas).toContain("puntos");
    expect(prisma.$queryRaw).not.toHaveBeenCalled();
  });

  it("validates the metric against the player's sport (a futbol key is unknown for NBA)", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(ref(JUGADOR, "BASQUETBOL") as never);
    const res = await request(app)
      .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=goles`)
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
  });

  it("returns 400 without metrica, for a bad n, a non-uuid id, and 404 for a missing player", async () => {
    const { app, prisma } = buildApp();
    expect(
      (await request(app).get(`/api/jugadores/${JUGADOR}/tendencia`).set("Authorization", bearer()))
        .status,
    ).toBe(400);
    expect(
      (
        await request(app)
          .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=puntos&n=0`)
          .set("Authorization", bearer())
      ).status,
    ).toBe(400);
    expect(
      (
        await request(app)
          .get("/api/jugadores/xyz/tendencia?metrica=puntos")
          .set("Authorization", bearer())
      ).status,
    ).toBe(400);
    prisma.jugador.findUnique.mockResolvedValue(null);
    expect(
      (
        await request(app)
          .get(`/api/jugadores/${JUGADOR}/tendencia?metrica=puntos`)
          .set("Authorization", bearer())
      ).status,
    ).toBe(404);
  });

  it("requires a token", async () => {
    const { app } = buildApp();
    expect(
      (await request(app).get(`/api/jugadores/${JUGADOR}/tendencia?metrica=puntos`)).status,
    ).toBe(401);
  });
});

describe("GET /api/jugadores/comparar", () => {
  it("returns each player's ref and averages in the requested order", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findMany.mockResolvedValue([ref(OTRO), ref(JUGADOR)] as never);
    prisma.$queryRaw
      .mockResolvedValueOnce([{ partidos: 2, minutosPromedio: 35 }] as never)
      .mockResolvedValueOnce([{ metrica: "puntos", promedio: 25 }] as never)
      .mockResolvedValueOnce([{ partidos: 4, minutosPromedio: 20 }] as never)
      .mockResolvedValueOnce([{ metrica: "puntos", promedio: 9 }] as never);
    const res = await request(app)
      .get(`/api/jugadores/comparar?ids=${JUGADOR},${OTRO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.deporte).toBe("BASQUETBOL");
    expect(res.body.jugadores.map((j: { jugador: { id: string } }) => j.jugador.id)).toEqual([
      JUGADOR,
      OTRO,
    ]);
    expect(res.body.jugadores[0]).toMatchObject({
      partidos: 2,
      minutosPromedio: 35,
      promedios: { puntos: 25 },
    });
    expect(res.body.jugadores[1].promedios.puntos).toBe(9);
  });

  it("accepts up to four ids and trims whitespace", async () => {
    const { app, prisma } = buildApp();
    const cuatro = [JUGADOR, OTRO, TERCERO, PARTIDO];
    prisma.jugador.findMany.mockResolvedValue(cuatro.map((id) => ref(id)) as never);
    prisma.$queryRaw.mockResolvedValue([{ partidos: 0, minutosPromedio: null }] as never);
    const res = await request(app)
      .get(`/api/jugadores/comparar?ids=${cuatro.join(", ")}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.jugadores).toHaveLength(4);
  });

  it("returns 400 for fewer than two, more than four, duplicate or malformed ids", async () => {
    const { app, prisma } = buildApp();
    const cinco = [JUGADOR, OTRO, TERCERO, PARTIDO, "11111111-1111-4111-8111-111111111111"];
    for (const ids of [
      JUGADOR,
      "",
      `${JUGADOR},${JUGADOR}`,
      cinco.join(","),
      `${JUGADOR},no-es-uuid`,
    ]) {
      const res = await request(app)
        .get(`/api/jugadores/comparar?ids=${ids}`)
        .set("Authorization", bearer());
      expect(res.status).toBe(400);
    }
    expect(
      (await request(app).get("/api/jugadores/comparar").set("Authorization", bearer())).status,
    ).toBe(400);
    expect(prisma.jugador.findMany).not.toHaveBeenCalled();
  });

  it("returns 400 when the players are from different sports", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findMany.mockResolvedValue([
      ref(JUGADOR, "BASQUETBOL"),
      ref(OTRO, "FUTBOL"),
    ] as never);
    const res = await request(app)
      .get(`/api/jugadores/comparar?ids=${JUGADOR},${OTRO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
    expect(res.body.error.message).toContain("mismo deporte");
    expect(prisma.$queryRaw).not.toHaveBeenCalled();
  });

  it("returns 404 when any player is missing", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findMany.mockResolvedValue([ref(JUGADOR)] as never);
    const res = await request(app)
      .get(`/api/jugadores/comparar?ids=${JUGADOR},${OTRO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("requires a token and is not captured by GET /:id", async () => {
    const { app, prisma } = buildApp();
    expect((await request(app).get(`/api/jugadores/comparar?ids=${JUGADOR},${OTRO}`)).status).toBe(
      401,
    );
    prisma.jugador.findMany.mockResolvedValue([] as never);
    const res = await request(app)
      .get(`/api/jugadores/comparar?ids=${JUGADOR},${OTRO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
    expect(prisma.jugador.findUnique).not.toHaveBeenCalled();
  });
});
