import request from "supertest";
import { Prisma } from "@prisma/client";
import { USER_ID, bearer, buildApp } from "./helpers";

const LISTA = "11111111-aaaa-4aaa-8aaa-111111111111";
const JUGADOR = "77777777-7777-4777-8777-777777777777";
const EQUIPO = "88888888-8888-4888-8888-888888888888";
const OTRO_USUARIO = "33333333-aaaa-4aaa-8aaa-333333333333";

const lista = (over: Record<string, unknown> = {}) => ({
  id: LISTA,
  usuarioId: USER_ID,
  nombre: "Favoritos",
  creadoEn: new Date(),
  ...over,
});

const p2002 = () =>
  new Prisma.PrismaClientKnownRequestError("dup", { code: "P2002", clientVersion: "5.22.0" });

describe("/api/listas ownership", () => {
  it("requires a token", async () => {
    const { app } = buildApp();
    expect((await request(app).get("/api/listas")).status).toBe(401);
  });

  it("lists only the caller's lists; ADMIN lists all", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findMany.mockResolvedValue([lista()] as never);
    prisma.listaSeguimiento.count.mockResolvedValue(1);

    const usuario = await request(app).get("/api/listas").set("Authorization", bearer());
    expect(usuario.status).toBe(200);
    expect(prisma.listaSeguimiento.findMany).toHaveBeenLastCalledWith(
      expect.objectContaining({ where: { usuarioId: USER_ID } }),
    );

    const admin = await request(app).get("/api/listas").set("Authorization", bearer("ADMIN"));
    expect(admin.status).toBe(200);
    expect(prisma.listaSeguimiento.findMany).toHaveBeenLastCalledWith(
      expect.objectContaining({ where: {} }),
    );
  });

  it("creates a list owned by the token's user, ignoring any usuarioId in the body", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.create.mockResolvedValue(lista() as never);
    const res = await request(app)
      .post("/api/listas")
      .set("Authorization", bearer())
      .send({ nombre: "Favoritos", usuarioId: OTRO_USUARIO });
    expect(res.status).toBe(201);
    expect(prisma.listaSeguimiento.create).toHaveBeenCalledWith({
      data: { nombre: "Favoritos", usuarioId: USER_ID },
    });
  });

  it("rejects an empty name", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .post("/api/listas")
      .set("Authorization", bearer())
      .send({ nombre: "" });
    expect(res.status).toBe(400);
  });

  it("GET /:id includes elementos for the owner", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue({
      ...lista(),
      elementos: [{ id: "e1", tipo: "JUGADOR", refId: JUGADOR, listaId: LISTA }],
    } as never);
    const res = await request(app).get(`/api/listas/${LISTA}`).set("Authorization", bearer());
    expect(res.status).toBe(200);
    expect(res.body.elementos).toHaveLength(1);
    expect(prisma.listaSeguimiento.findUnique).toHaveBeenCalledWith(
      expect.objectContaining({ include: { elementos: true } }),
    );
  });

  it("another user's list is 404 for reads and writes", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(
      lista({ usuarioId: OTRO_USUARIO }) as never,
    );
    const auth = bearer();
    expect((await request(app).get(`/api/listas/${LISTA}`).set("Authorization", auth)).status).toBe(
      404,
    );
    expect(
      (
        await request(app)
          .put(`/api/listas/${LISTA}`)
          .set("Authorization", auth)
          .send({ nombre: "x" })
      ).status,
    ).toBe(404);
    expect(
      (await request(app).delete(`/api/listas/${LISTA}`).set("Authorization", auth)).status,
    ).toBe(404);
    expect(
      (
        await request(app)
          .post(`/api/listas/${LISTA}/elementos`)
          .set("Authorization", auth)
          .send({ tipo: "JUGADOR", refId: JUGADOR })
      ).status,
    ).toBe(404);
    expect(prisma.listaSeguimiento.update).not.toHaveBeenCalled();
    expect(prisma.listaSeguimiento.delete).not.toHaveBeenCalled();
    expect(prisma.elementoLista.create).not.toHaveBeenCalled();
  });

  it("ADMIN can read another user's list but not change it", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(
      lista({ usuarioId: OTRO_USUARIO }) as never,
    );
    const admin = bearer("ADMIN");
    expect(
      (await request(app).get(`/api/listas/${LISTA}`).set("Authorization", admin)).status,
    ).toBe(200);
    expect(
      (await request(app).delete(`/api/listas/${LISTA}`).set("Authorization", admin)).status,
    ).toBe(404);
  });

  it("returns 404 for a missing list and 400 for a malformed id", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(null);
    expect(
      (await request(app).get(`/api/listas/${LISTA}`).set("Authorization", bearer())).status,
    ).toBe(404);
    expect((await request(app).get("/api/listas/nope").set("Authorization", bearer())).status).toBe(
      400,
    );
  });

  it("PUT and DELETE on the owner's list succeed", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.listaSeguimiento.update.mockResolvedValue(lista({ nombre: "Nueva" }) as never);
    prisma.listaSeguimiento.delete.mockResolvedValue(lista() as never);
    const put = await request(app)
      .put(`/api/listas/${LISTA}`)
      .set("Authorization", bearer())
      .send({ nombre: "Nueva" });
    expect(put.status).toBe(200);
    const del = await request(app).delete(`/api/listas/${LISTA}`).set("Authorization", bearer());
    expect(del.status).toBe(204);
  });
});

describe("/api/listas/:id/elementos", () => {
  it("adds a jugador that exists", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.jugador.findUnique.mockResolvedValue({ id: JUGADOR } as never);
    prisma.elementoLista.create.mockResolvedValue({
      id: "e1",
      listaId: LISTA,
      tipo: "JUGADOR",
      refId: JUGADOR,
    } as never);
    const res = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "JUGADOR", refId: JUGADOR });
    expect(res.status).toBe(201);
    expect(prisma.elementoLista.create).toHaveBeenCalledWith({
      data: { listaId: LISTA, tipo: "JUGADOR", refId: JUGADOR },
    });
  });

  it("adds an equipo that exists", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.equipo.findUnique.mockResolvedValue({ id: EQUIPO } as never);
    prisma.elementoLista.create.mockResolvedValue({ id: "e2" } as never);
    const res = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "EQUIPO", refId: EQUIPO });
    expect(res.status).toBe(201);
    expect(prisma.jugador.findUnique).not.toHaveBeenCalled();
  });

  it("404 when the referenced jugador or equipo does not exist", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.jugador.findUnique.mockResolvedValue(null);
    prisma.equipo.findUnique.mockResolvedValue(null);
    const jugador = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "JUGADOR", refId: JUGADOR });
    expect(jugador.status).toBe(404);
    expect(jugador.body.error.message).toMatch(/Jugador/);
    const equipo = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "EQUIPO", refId: EQUIPO });
    expect(equipo.status).toBe(404);
    expect(equipo.body.error.message).toMatch(/Equipo/);
    expect(prisma.elementoLista.create).not.toHaveBeenCalled();
  });

  it("409 when the element is already in the list", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.jugador.findUnique.mockResolvedValue({ id: JUGADOR } as never);
    prisma.elementoLista.create.mockRejectedValue(p2002());
    const res = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "JUGADOR", refId: JUGADOR });
    expect(res.status).toBe(409);
    expect(res.body.error.code).toBe("DUPLICATE");
  });

  it("rejects an unknown tipo or a malformed refId with 400", async () => {
    const { app } = buildApp();
    const tipo = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "PARTIDO", refId: JUGADOR });
    expect(tipo.status).toBe(400);
    const ref = await request(app)
      .post(`/api/listas/${LISTA}/elementos`)
      .set("Authorization", bearer())
      .send({ tipo: "JUGADOR", refId: "abc" });
    expect(ref.status).toBe(400);
  });

  it("DELETE /:id/elementos/:ref removes by refId and returns 204", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.elementoLista.deleteMany.mockResolvedValue({ count: 1 });
    const res = await request(app)
      .delete(`/api/listas/${LISTA}/elementos/${JUGADOR}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(204);
    expect(prisma.elementoLista.deleteMany).toHaveBeenCalledWith({
      where: { listaId: LISTA, refId: JUGADOR },
    });
  });

  it("DELETE /:id/elementos/:ref is 404 when the element is not in the list", async () => {
    const { app, prisma } = buildApp();
    prisma.listaSeguimiento.findUnique.mockResolvedValue(lista() as never);
    prisma.elementoLista.deleteMany.mockResolvedValue({ count: 0 });
    const res = await request(app)
      .delete(`/api/listas/${LISTA}/elementos/${JUGADOR}`)
      .set("Authorization", bearer());
    expect(res.status).toBe(404);
  });

  it("DELETE /:id/elementos/:ref rejects a malformed ref", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .delete(`/api/listas/${LISTA}/elementos/no-uuid`)
      .set("Authorization", bearer());
    expect(res.status).toBe(400);
  });
});
