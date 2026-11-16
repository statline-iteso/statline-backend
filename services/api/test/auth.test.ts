import request from "supertest";
import { hashPassword } from "../src/lib/auth";
import { ADMIN_ID, USER_ID, bearer, buildApp, tokens } from "./helpers";

const usuario = {
  id: USER_ID,
  email: "ana@example.com",
  nombre: "Ana",
  rol: "USUARIO" as const,
  creadoEn: new Date(),
  actualizadoEn: new Date(),
};

describe("POST /api/auth/login", () => {
  it("returns tokens for valid credentials", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue({
      ...usuario,
      passwordHash: await hashPassword("secreto123"),
    });
    const res = await request(app)
      .post("/api/auth/login")
      .send({ email: usuario.email, password: "secreto123" });
    expect(res.status).toBe(200);
    expect(tokens.verifyAccess(res.body.accessToken)).toMatchObject({
      sub: USER_ID,
      rol: "USUARIO",
    });
    expect(res.body.usuario).not.toHaveProperty("passwordHash");
  });

  it("rejects a wrong password with 401", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue({
      ...usuario,
      passwordHash: await hashPassword("secreto123"),
    });
    const res = await request(app)
      .post("/api/auth/login")
      .send({ email: usuario.email, password: "otra" });
    expect(res.status).toBe(401);
  });

  it("rejects an unknown email with the same 401", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .post("/api/auth/login")
      .send({ email: "x@example.com", password: "secreto123" });
    expect(res.status).toBe(401);
    expect(res.body.error.message).toBe("Credenciales inválidas");
  });

  it("validates the body", async () => {
    const { app } = buildApp();
    const res = await request(app).post("/api/auth/login").send({ email: "no-es-email" });
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("VALIDATION_ERROR");
  });
});

describe("POST /api/auth/refresh", () => {
  it("issues new tokens with the current role", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue({ ...usuario, rol: "ANALISTA", passwordHash: "" });
    const refreshToken = tokens.signRefresh({ sub: USER_ID, rol: "USUARIO" });
    const res = await request(app).post("/api/auth/refresh").send({ refreshToken });
    expect(res.status).toBe(200);
    expect(tokens.verifyAccess(res.body.accessToken).rol).toBe("ANALISTA");
  });

  it("rejects an access token used as refresh token", async () => {
    const { app } = buildApp();
    const res = await request(app)
      .post("/api/auth/refresh")
      .send({ refreshToken: tokens.signAccess({ sub: USER_ID, rol: "USUARIO" }) });
    expect(res.status).toBe(401);
  });

  it("rejects a refresh token for a deleted user", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue(null);
    const refreshToken = tokens.signRefresh({ sub: USER_ID, rol: "USUARIO" });
    const res = await request(app).post("/api/auth/refresh").send({ refreshToken });
    expect(res.status).toBe(401);
  });
});

describe("/api/usuarios", () => {
  it("POST registers a USUARIO and never returns the hash", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.create.mockResolvedValue(usuario as never);
    const res = await request(app)
      .post("/api/usuarios")
      .send({ email: usuario.email, nombre: "Ana", password: "secreto123" });
    expect(res.status).toBe(201);
    const args = prisma.usuario.create.mock.calls[0]![0];
    expect(args.data.passwordHash).not.toBe("secreto123");
    expect(args.data).not.toHaveProperty("rol");
  });

  it("GET list requires ADMIN", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findMany.mockResolvedValue([]);
    prisma.usuario.count.mockResolvedValue(0);
    expect((await request(app).get("/api/usuarios")).status).toBe(401);
    expect((await request(app).get("/api/usuarios").set("Authorization", bearer())).status).toBe(
      403,
    );
    const ok = await request(app).get("/api/usuarios").set("Authorization", bearer("ADMIN"));
    expect(ok.status).toBe(200);
    expect(ok.body).toEqual({ data: [], total: 0, page: 1, pageSize: 20 });
  });

  it("a user can read themselves but not another user", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue(usuario as never);
    const self = await request(app).get(`/api/usuarios/${USER_ID}`).set("Authorization", bearer());
    expect(self.status).toBe(200);
    const other = await request(app)
      .get(`/api/usuarios/${ADMIN_ID}`)
      .set("Authorization", bearer());
    expect(other.status).toBe(403);
  });

  it("GET /:id is 404 when missing", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.findUnique.mockResolvedValue(null);
    const res = await request(app)
      .get(`/api/usuarios/${USER_ID}`)
      .set("Authorization", bearer("ADMIN"));
    expect(res.status).toBe(404);
  });

  it("only ADMIN can change a role", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.update.mockResolvedValue(usuario as never);
    const res = await request(app)
      .put(`/api/usuarios/${USER_ID}`)
      .set("Authorization", bearer())
      .send({ rol: "ADMIN" });
    expect(res.status).toBe(403);
    const admin = await request(app)
      .put(`/api/usuarios/${USER_ID}`)
      .set("Authorization", bearer("ADMIN"))
      .send({ rol: "ANALISTA", password: "nuevo-secreto" });
    expect(admin.status).toBe(200);
  });

  it("DELETE is ADMIN only and returns 204", async () => {
    const { app, prisma } = buildApp();
    prisma.usuario.delete.mockResolvedValue(usuario as never);
    expect(
      (await request(app).delete(`/api/usuarios/${USER_ID}`).set("Authorization", bearer())).status,
    ).toBe(403);
    expect(
      (await request(app).delete(`/api/usuarios/${USER_ID}`).set("Authorization", bearer("ADMIN")))
        .status,
    ).toBe(204);
  });

  it("rejects a malformed bearer token", async () => {
    const { app } = buildApp();
    const res = await request(app).get("/api/ligas").set("Authorization", "Bearer basura");
    expect(res.status).toBe(401);
  });
});
