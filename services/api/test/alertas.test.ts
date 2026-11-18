import request from "supertest";
import { Prisma, type Alerta } from "@prisma/client";
import { USER_ID, bearer, buildApp } from "./helpers";

const ALERTA_ID = "77777777-7777-4777-8777-777777777777";
const JUGADOR_ID = "88888888-8888-4888-8888-888888888888";
const EQUIPO_ID = "99999999-9999-4999-8999-999999999999";
const OTRO_USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const alerta = (over: Partial<Alerta> = {}): Alerta => ({
  id: ALERTA_ID,
  usuarioId: USER_ID,
  tipo: "LESION" as const,
  jugadorId: JUGADOR_ID,
  equipoId: null,
  condicion: null,
  activa: true,
  ultimaDisparada: null,
  creadoEn: new Date("2026-11-01T00:00:00Z"),
  ...over,
});

const umbral = {
  tipo: "UMBRAL",
  jugadorId: JUGADOR_ID,
  condicion: { metrica: "puntos", operador: ">=", valor: 30 },
};

describe("/api/alertas", () => {
  it("requires a token", async () => {
    const { app } = buildApp();
    expect((await request(app).get("/api/alertas")).status).toBe(401);
  });

  it("lists only the caller's alerts; ADMIN lists all", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findMany.mockResolvedValue([alerta()]);
    prisma.alerta.count.mockResolvedValue(1);

    const user = await request(app)
      .get("/api/alertas?page=1&pageSize=5")
      .set("Authorization", bearer());
    expect(user.status).toBe(200);
    expect(user.body).toMatchObject({ total: 1, page: 1, pageSize: 5 });
    expect(prisma.alerta.findMany).toHaveBeenLastCalledWith(
      expect.objectContaining({ where: { usuarioId: USER_ID }, orderBy: { creadoEn: "desc" } }),
    );

    const admin = await request(app).get("/api/alertas").set("Authorization", bearer("ADMIN"));
    expect(admin.status).toBe(200);
    expect(prisma.alerta.findMany).toHaveBeenLastCalledWith(expect.objectContaining({ where: {} }));
  });

  it("creates a LESION alert for the JWT user after checking the jugador exists", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue({ id: JUGADOR_ID } as never);
    prisma.alerta.create.mockResolvedValue(alerta());
    const res = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "LESION", jugadorId: JUGADOR_ID });
    expect(res.status).toBe(201);
    expect(prisma.alerta.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        usuarioId: USER_ID,
        tipo: "LESION",
        jugadorId: JUGADOR_ID,
        equipoId: null,
        condicion: Prisma.DbNull,
        activa: true,
      }),
    });
  });

  it("LESION requires jugadorId", async () => {
    const { app, prisma } = buildApp();
    const res = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "LESION", equipoId: EQUIPO_ID });
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_ERROR");
    expect(prisma.alerta.create).not.toHaveBeenCalled();
  });

  it("INICIO_PARTIDO accepts jugadorId or equipoId but not neither", async () => {
    const { app, prisma } = buildApp();
    prisma.equipo.findUnique.mockResolvedValue({ id: EQUIPO_ID } as never);
    prisma.alerta.create.mockResolvedValue(
      alerta({ tipo: "INICIO_PARTIDO", jugadorId: null, equipoId: EQUIPO_ID }),
    );

    const ok = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "INICIO_PARTIDO", equipoId: EQUIPO_ID });
    expect(ok.status).toBe(201);
    expect(prisma.alerta.create).toHaveBeenCalledWith({
      data: expect.objectContaining({ jugadorId: null, equipoId: EQUIPO_ID }),
    });

    const none = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "INICIO_PARTIDO" });
    expect(none.status).toBe(400);
  });

  it("UMBRAL requires jugadorId and a valid condicion", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue({ id: JUGADOR_ID } as never);
    prisma.alerta.create.mockResolvedValue(alerta({ tipo: "UMBRAL", condicion: umbral.condicion }));

    const ok = await request(app).post("/api/alertas").set("Authorization", bearer()).send(umbral);
    expect(ok.status).toBe(201);
    expect(prisma.alerta.create).toHaveBeenCalledWith({
      data: expect.objectContaining({ condicion: umbral.condicion }),
    });

    const sinCondicion = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "UMBRAL", jugadorId: JUGADOR_ID });
    expect(sinCondicion.status).toBe(400);

    const operadorInvalido = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ ...umbral, condicion: { ...umbral.condicion, operador: "!=" } });
    expect(operadorInvalido.status).toBe(400);

    const valorNoNumerico = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ ...umbral, condicion: { ...umbral.condicion, valor: "30" } });
    expect(valorNoNumerico.status).toBe(400);
  });

  it("rejects an unknown tipo", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "OTRO", jugadorId: JUGADOR_ID });
    expect(res.status).toBe(400);
  });

  it("answers 400 with the field when the referenced jugador or equipo does not exist", async () => {
    const { app, prisma } = buildApp();
    prisma.jugador.findUnique.mockResolvedValue(null);
    prisma.equipo.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .post("/api/alertas")
      .set("Authorization", bearer())
      .send({ tipo: "INICIO_PARTIDO", jugadorId: JUGADOR_ID, equipoId: EQUIPO_ID });
    expect(res.status).toBe(400);
    expect(res.body.error.details).toEqual([
      { path: "jugadorId", message: "El jugador no existe" },
      { path: "equipoId", message: "El equipo no existe" },
    ]);
    expect(prisma.alerta.create).not.toHaveBeenCalled();
  });

  it("GET /:id returns own alert, 403 for someone else's, ADMIN can read any", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta());
    expect(
      (await request(app).get(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer())).status,
    ).toBe(200);

    prisma.alerta.findUnique.mockResolvedValue(alerta({ usuarioId: OTRO_USER }));
    expect(
      (await request(app).get(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer())).status,
    ).toBe(403);
    expect(
      (await request(app).get(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer("ADMIN")))
        .status,
    ).toBe(200);
  });

  it("GET /:id is 404 when missing and 400 for a non-uuid id", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).get(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer())).status,
    ).toBe(404);
    expect(
      (await request(app).get("/api/alertas/nope").set("Authorization", bearer())).status,
    ).toBe(400);
  });

  it("PUT with only activa toggles the alert", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta());
    prisma.alerta.update.mockResolvedValue(alerta({ activa: false }));
    const res = await request(app)
      .put(`/api/alertas/${ALERTA_ID}`)
      .set("Authorization", bearer())
      .send({ activa: false });
    expect(res.status).toBe(200);
    expect(prisma.alerta.update).toHaveBeenCalledWith({
      where: { id: ALERTA_ID },
      data: { activa: false },
    });
  });

  it("PUT with a full definition validates it and replaces the fields", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta());
    prisma.jugador.findUnique.mockResolvedValue({ id: JUGADOR_ID } as never);
    prisma.alerta.update.mockResolvedValue(alerta({ tipo: "UMBRAL" }));
    const res = await request(app)
      .put(`/api/alertas/${ALERTA_ID}`)
      .set("Authorization", bearer())
      .send(umbral);
    expect(res.status).toBe(200);
    expect(prisma.alerta.update).toHaveBeenCalledWith({
      where: { id: ALERTA_ID },
      data: expect.objectContaining({
        tipo: "UMBRAL",
        jugadorId: JUGADOR_ID,
        equipoId: null,
        condicion: umbral.condicion,
      }),
    });
  });

  it("PUT rejects an empty body and an invalid full definition", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta());
    expect(
      (await request(app).put(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer()).send({}))
        .status,
    ).toBe(400);
    expect(
      (
        await request(app)
          .put(`/api/alertas/${ALERTA_ID}`)
          .set("Authorization", bearer())
          .send({ tipo: "UMBRAL", jugadorId: JUGADOR_ID })
      ).status,
    ).toBe(400);
    expect(prisma.alerta.update).not.toHaveBeenCalled();
  });

  it("PUT and DELETE are owner-only, even for ADMIN", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta({ usuarioId: OTRO_USER }));
    expect(
      (
        await request(app)
          .put(`/api/alertas/${ALERTA_ID}`)
          .set("Authorization", bearer("ADMIN"))
          .send({ activa: false })
      ).status,
    ).toBe(403);
    expect(
      (await request(app).delete(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer("ADMIN")))
        .status,
    ).toBe(403);
    expect(prisma.alerta.update).not.toHaveBeenCalled();
    expect(prisma.alerta.delete).not.toHaveBeenCalled();
  });

  it("DELETE removes the caller's alert with 204 and 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.alerta.findUnique.mockResolvedValue(alerta());
    prisma.alerta.delete.mockResolvedValue(alerta());
    expect(
      (await request(app).delete(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer()))
        .status,
    ).toBe(204);
    expect(prisma.alerta.delete).toHaveBeenCalledWith({ where: { id: ALERTA_ID } });

    prisma.alerta.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).delete(`/api/alertas/${ALERTA_ID}`).set("Authorization", bearer()))
        .status,
    ).toBe(404);
  });
});
