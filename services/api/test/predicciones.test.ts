import request from "supertest";
import { bearer, buildApp } from "./helpers";
import { AppError } from "../src/lib/errors";
import { createPrediccionesClient } from "../src/lib/predicciones";

const PARTIDO = "66666666-6666-4666-8666-666666666666";
const MODELO = "77777777-7777-4777-8777-777777777777";
const JUGADOR = "88888888-8888-4888-8888-888888888888";

describe("/api/pronosticos", () => {
  it("lists the newest forecast per game with filters and a total", async () => {
    const { app, prisma } = buildApp();
    prisma.pronosticoPartido.findMany
      .mockResolvedValueOnce([{ id: "p1", partidoId: PARTIDO }] as never)
      .mockResolvedValueOnce([{ id: "p1" }, { id: "p2" }] as never);
    const res = await request(app)
      .get(`/api/pronosticos?deporte=BASQUETBOL&jornada=3&partidoId=${PARTIDO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ total: 2, page: 1, pageSize: 20 });
    const args = prisma.pronosticoPartido.findMany.mock.calls[0]![0] as never as {
      where: unknown;
      distinct: string[];
    };
    expect(args.distinct).toEqual(["partidoId"]);
    expect(args.where).toEqual({
      partido: { liga: { deporte: "BASQUETBOL" }, jornada: 3 },
      partidoId: PARTIDO,
    });
  });

  it("GET /:id is 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.pronosticoPartido.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/pronosticos/${PARTIDO}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("GET /precision proxies with the fixed tipo and passes the answer through", async () => {
    const { app, predicciones } = buildApp();
    predicciones.get.mockResolvedValue({ status: 200, body: { precision: { n: 3 } } });
    const res = await request(app)
      .get("/api/pronosticos/precision?deporte=FUTBOL")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ precision: { n: 3 } });
    expect(predicciones.get).toHaveBeenCalledWith("/precision", {
      deporte: "FUTBOL",
      tipo: "RESULTADO_PARTIDO",
    });
  });

  it("GET /precision rejects the other tipo", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .get("/api/pronosticos/precision?deporte=FUTBOL&tipo=PROYECCION_JUGADOR")
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
  });

  it("POST /generar: ANALISTA or ADMIN only, camelCase body mapped to snake_case", async () => {
    const { app, predicciones } = buildApp();
    predicciones.post.mockResolvedValue({ status: 200, body: { generados: 1 } });
    const body = { deporte: "BASQUETBOL", partidoIds: [PARTIDO] };
    expect(
      (
        await request(app)
          .post("/api/pronosticos/generar")
          .set("Authorization", bearer())
          .send(body)
      ).status,
    ).toBe(403);
    const ok = await request(app)
      .post("/api/pronosticos/generar")
      .set("Authorization", bearer("ANALISTA"))
      .send(body);
    expect(ok.status).toBe(200);
    expect(predicciones.post).toHaveBeenCalledWith("/pronosticos/generar", {
      deporte: "BASQUETBOL",
      jornada: undefined,
      partido_ids: [PARTIDO],
    });
  });

  it("forwards predicciones' error status and body (e.g. 409 NO_ACTIVE_MODEL)", async () => {
    const { app, predicciones } = buildApp();
    const err = { error: { code: "NO_ACTIVE_MODEL", message: "x" } };
    predicciones.post.mockResolvedValue({ status: 409, body: err });
    const res = await request(app)
      .post("/api/pronosticos/generar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "FUTBOL" });
    expect(res.status).toBe(409);
    expect(res.body).toEqual(err);
  });

  it("maps an unreachable predicciones to 503 PREDICCIONES_UNAVAILABLE", async () => {
    const { app, predicciones } = buildApp();
    predicciones.post.mockRejectedValue(
      new AppError("PREDICCIONES_UNAVAILABLE", 503, "no responde"),
    );
    const res = await request(app)
      .post("/api/pronosticos/generar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "FUTBOL" });
    expect(res.status).toBe(503);
    expect(res.body.error.code).toBe("PREDICCIONES_UNAVAILABLE");
  });
});

describe("/api/proyecciones", () => {
  it("lists with ?jugadorId= and ?jornada=", async () => {
    const { app, prisma } = buildApp();
    prisma.proyeccionJugador.findMany.mockResolvedValue([]);
    prisma.proyeccionJugador.count.mockResolvedValue(0);
    const res = await request(app)
      .get(`/api/proyecciones?jornada=5&jugadorId=${JUGADOR}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(prisma.proyeccionJugador.findMany.mock.calls[0]![0]!.where).toEqual({
      partido: { jornada: 5 },
      jugadorId: JUGADOR,
    });
  });

  it("filters by ?deporte= through the partido's liga", async () => {
    const { app, prisma } = buildApp();
    prisma.proyeccionJugador.findMany.mockResolvedValue([]);
    prisma.proyeccionJugador.count.mockResolvedValue(0);
    const res = await request(app)
      .get("/api/proyecciones?deporte=AMERICANO&jornada=3")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(prisma.proyeccionJugador.findMany.mock.calls[0]![0]!.where).toEqual({
      partido: { liga: { deporte: "AMERICANO" }, jornada: 3 },
    });
  });

  it("GET /:id is 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.proyeccionJugador.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/proyecciones/${JUGADOR}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("GET /precision fixes tipo to PROYECCION_JUGADOR", async () => {
    const { app, predicciones } = buildApp();
    predicciones.get.mockResolvedValue({ status: 200, body: {} });
    await request(app)
      .get("/api/proyecciones/precision?deporte=BASQUETBOL")
      .set("Authorization", bearer());
    expect(predicciones.get).toHaveBeenCalledWith("/precision", {
      deporte: "BASQUETBOL",
      tipo: "PROYECCION_JUGADOR",
    });
  });

  it("POST /generar maps jugadorIds to jugador_ids", async () => {
    const { app, predicciones } = buildApp();
    predicciones.post.mockResolvedValue({ status: 200, body: { generados: 0 } });
    const res = await request(app)
      .post("/api/proyecciones/generar")
      .set("Authorization", bearer("ANALISTA"))
      .send({ deporte: "BASQUETBOL", jugadorIds: [JUGADOR] });
    expect(res.status).toBe(200);
    expect(predicciones.post).toHaveBeenCalledWith("/proyecciones/generar", {
      deporte: "BASQUETBOL",
      jornada: undefined,
      jugador_ids: [JUGADOR],
    });
  });
});

describe("/api/modelos", () => {
  it("lists models without artifact bytes", async () => {
    const { app, prisma } = buildApp();
    prisma.modeloPrediccion.findMany.mockResolvedValue([{ id: MODELO }] as never);
    prisma.modeloPrediccion.count.mockResolvedValue(1);
    const res = await request(app)
      .get("/api/modelos?deporte=FUTBOL&tipo=RESULTADO_PARTIDO")
      .set("Authorization", bearer());
    expect(res.status).toBe(200);
    const args = prisma.modeloPrediccion.findMany.mock.calls[0]![0]! as {
      where: unknown;
      include?: unknown;
    };
    expect(args.where).toEqual({ deporte: "FUTBOL", tipo: "RESULTADO_PARTIDO" });
    expect(args.include).toBeUndefined();
  });

  it("GET /:id is 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.modeloPrediccion.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).get(`/api/modelos/${MODELO}`).set("Authorization", bearer())).status,
    ).toBe(404);
  });

  it("activar and reentrenar are ADMIN only", async () => {
    const { app, predicciones } = buildApp();
    predicciones.post.mockResolvedValue({ status: 200, body: { activo: true } });
    expect(
      (
        await request(app)
          .post(`/api/modelos/${MODELO}/activar`)
          .set("Authorization", bearer("ANALISTA"))
      ).status,
    ).toBe(403);
    expect(
      (
        await request(app)
          .post("/api/modelos/reentrenar")
          .set("Authorization", bearer("ANALISTA"))
          .send({})
      ).status,
    ).toBe(403);
    const act = await request(app)
      .post(`/api/modelos/${MODELO}/activar`)
      .set("Authorization", bearer("ADMIN"));
    expect(act.status).toBe(200);
    expect(predicciones.post).toHaveBeenCalledWith(`/modelos/${MODELO}/activar`);
    const re = await request(app)
      .post("/api/modelos/reentrenar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "AMERICANO", tipo: "PROYECCION_JUGADOR" });
    expect(re.status).toBe(200);
    expect(predicciones.post).toHaveBeenLastCalledWith("/modelos/reentrenar", {
      deporte: "AMERICANO",
      tipo: "PROYECCION_JUGADOR",
    });
  });

  it("has no standard write routes", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .put(`/api/modelos/${MODELO}`)
      .set("Authorization", bearer("ADMIN"))
      .send({});
    expect(res.status).toBe(404);
  });
});

describe("createPrediccionesClient", () => {
  const base = "http://predicciones:8000";

  it("sends query and JSON body and returns status and body unchanged", async () => {
    const fetchImpl = jest.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 202 }));
    const client = createPrediccionesClient({ baseUrl: base, timeoutMs: 1000, fetchImpl });
    const r = await client.get("/precision", { deporte: "FUTBOL", tipo: "RESULTADO_PARTIDO" });
    expect(r).toEqual({ status: 202, body: { ok: 1 } });
    const [url] = fetchImpl.mock.calls[0] as unknown as [URL];
    expect(url.toString()).toBe(`${base}/precision?deporte=FUTBOL&tipo=RESULTADO_PARTIDO`);
    await client.post("/x", { a: 1 });
    const init = (fetchImpl.mock.calls[1] as unknown as [URL, RequestInit])[1];
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"a":1}');
  });

  it("maps a connection error to 503", async () => {
    const fetchImpl = jest.fn(async () => {
      throw new TypeError("fetch failed");
    });
    const client = createPrediccionesClient({ baseUrl: base, timeoutMs: 1000, fetchImpl });
    await expect(client.get("/precision")).rejects.toMatchObject({
      code: "PREDICCIONES_UNAVAILABLE",
      status: 503,
    });
  });

  it("maps a non-JSON answer to 502", async () => {
    const fetchImpl = jest.fn(async () => new Response("<html>", { status: 502 }));
    const client = createPrediccionesClient({ baseUrl: base, timeoutMs: 1000, fetchImpl });
    await expect(client.post("/x")).rejects.toMatchObject({ status: 502 });
  });
});
