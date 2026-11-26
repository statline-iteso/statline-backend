import { generateKeyPairSync, type KeyObject } from "node:crypto";
import jwt from "jsonwebtoken";
import request from "supertest";
import { Prisma } from "@prisma/client";
import { CognitoJwtVerifier } from "aws-jwt-verify";
import {
  crearAutenticadorCognito,
  identidadDesde,
  type Autenticador,
  type VerificadorCognito,
} from "../src/lib/cognito";
import { loadConfig } from "../src/config";
import { unauthorized } from "../src/lib/errors";
import { buildApp, USER_ID } from "./helpers";

const POOL = "us-east-1_TestPool1";
const CLIENT = "testclient123";
const ISS = `https://cognito-idp.us-east-1.amazonaws.com/${POOL}`;
const KID = "test-key";

const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const jwk = {
  ...(publicKey as KeyObject).export({ format: "jwk" }),
  kid: KID,
  alg: "RS256",
  use: "sig",
};

/** The real aws-jwt-verify verifier, with the JWKS cached so it never goes to the network. */
function verificadorLocal(): VerificadorCognito {
  const verifier = CognitoJwtVerifier.create({
    userPoolId: POOL,
    clientId: CLIENT,
    tokenUse: "id",
  });
  verifier.cacheJwks({ keys: [jwk as never] });
  return async (token) => identidadDesde(await verifier.verify(token));
}

function idToken(claims: Record<string, unknown> = {}, opts: { aud?: string; use?: string } = {}) {
  return jwt.sign(
    {
      sub: "cog-sub-1",
      email: "Ana@Example.com",
      email_verified: true,
      name: "Ana",
      token_use: opts.use ?? "id",
      ...claims,
    },
    privateKey,
    { algorithm: "RS256", keyid: KID, issuer: ISS, audience: opts.aud ?? CLIENT, expiresIn: "5m" },
  );
}

const fila = (over: Record<string, unknown> = {}) => ({
  id: USER_ID,
  email: "ana@example.com",
  nombre: "Ana",
  rol: "USUARIO" as const,
  passwordHash: null,
  cognitoSub: "cog-sub-1",
  creadoEn: new Date(),
  actualizadoEn: new Date(),
  ...over,
});

function autenticador() {
  const ctx = buildApp();
  const auth: Autenticador = crearAutenticadorCognito({
    prisma: ctx.prisma as never,
    verificar: verificadorLocal(),
  });
  return { prisma: ctx.prisma, auth };
}

describe("Cognito authentication (AUTH_MODE=cognito)", () => {
  it("accepts a valid ID token of a linked user and keeps its role from PostgreSQL", async () => {
    const { prisma, auth } = autenticador();
    prisma.usuario.findUnique.mockResolvedValueOnce(fila({ rol: "ANALISTA" }));
    await expect(auth(idToken())).resolves.toEqual({ sub: USER_ID, rol: "ANALISTA" });
    expect(prisma.usuario.findUnique).toHaveBeenCalledWith({ where: { cognitoSub: "cog-sub-1" } });
  });

  it("links an existing row by verified email (the seeded admin)", async () => {
    const { prisma, auth } = autenticador();
    prisma.usuario.findUnique.mockResolvedValueOnce(null);
    prisma.usuario.findUnique.mockResolvedValueOnce(fila({ rol: "ADMIN", cognitoSub: null }));
    prisma.usuario.update.mockResolvedValueOnce(fila({ rol: "ADMIN" }));
    await expect(auth(idToken())).resolves.toEqual({ sub: USER_ID, rol: "ADMIN" });
    expect(prisma.usuario.findUnique).toHaveBeenLastCalledWith({
      where: { email: "ana@example.com" },
    });
    expect(prisma.usuario.update).toHaveBeenCalledWith({
      where: { id: USER_ID },
      data: { cognitoSub: "cog-sub-1" },
    });
  });

  it("creates a USUARIO row on the first sign-in of a new user", async () => {
    const { prisma, auth } = autenticador();
    prisma.usuario.findUnique.mockResolvedValue(null);
    prisma.usuario.create.mockResolvedValueOnce(fila());
    await expect(auth(idToken({ name: undefined }))).resolves.toEqual({
      sub: USER_ID,
      rol: "USUARIO",
    });
    expect(prisma.usuario.create).toHaveBeenCalledWith({
      data: { email: "ana@example.com", nombre: "ana", cognitoSub: "cog-sub-1", rol: "USUARIO" },
    });
  });

  it("retries once when two first requests race on the insert", async () => {
    const { prisma, auth } = autenticador();
    prisma.usuario.findUnique.mockResolvedValueOnce(null).mockResolvedValueOnce(null);
    prisma.usuario.create.mockRejectedValueOnce(
      new Prisma.PrismaClientKnownRequestError("dup", { code: "P2002", clientVersion: "5" }),
    );
    prisma.usuario.findUnique.mockResolvedValueOnce(fila());
    await expect(auth(idToken())).resolves.toEqual({ sub: USER_ID, rol: "USUARIO" });
  });

  it.each([
    ["another client", () => idToken({}, { aud: "otro" })],
    ["an access token", () => idToken({}, { use: "access" })],
    ["garbage", () => "no.es.jwt"],
  ])("rejects %s with 401", async (_n, token) => {
    const { auth } = autenticador();
    await expect(auth(token())).rejects.toMatchObject({ status: 401 });
  });

  it("rejects an unverified email when the user is not linked yet", async () => {
    const { prisma, auth } = autenticador();
    prisma.usuario.findUnique.mockResolvedValue(null);
    await expect(auth(idToken({ email_verified: false }))).rejects.toMatchObject({ status: 401 });
    expect(prisma.usuario.create).not.toHaveBeenCalled();
  });
});

describe("routes in Cognito mode", () => {
  const conCognito = (rol: "USUARIO" | "ADMIN" = "USUARIO") =>
    buildApp({ cognito: async () => ({ sub: USER_ID, rol }) });

  it("serves authenticated routes with the Cognito claims", async () => {
    const { app, prisma } = conCognito();
    prisma.usuario.findUnique.mockResolvedValue(fila() as never);
    const res = await request(app).get(`/api/usuarios/${USER_ID}`).set("Authorization", "Bearer x");
    expect(res.status).toBe(200);
  });

  it("turns off /api/auth/login and the public sign-up", async () => {
    const { app } = conCognito();
    expect(
      (await request(app).post("/api/auth/login").send({ email: "a@b.co", password: "x" })).status,
    ).toBe(404);
    const alta = await request(app)
      .post("/api/usuarios")
      .send({ email: "a@b.co", nombre: "A", password: "12345678" });
    expect(alta.status).toBe(404);
  });

  it("refuses password changes (they belong to Cognito)", async () => {
    const { app } = conCognito();
    const res = await request(app)
      .put(`/api/usuarios/${USER_ID}`)
      .set("Authorization", "Bearer x")
      .send({ password: "nueva-clave-123" });
    expect(res.status).toBe(400);
  });

  it("answers 401 when the autenticador rejects", async () => {
    const { app } = buildApp({
      cognito: async () => {
        throw unauthorized();
      },
    });
    expect((await request(app).get("/api/ligas").set("Authorization", "Bearer x")).status).toBe(
      401,
    );
  });
});

describe("config", () => {
  const base = {
    DATABASE_URL: "postgresql://u:p@localhost:5432/db",
    JWT_SECRET: "x".repeat(16),
    JWT_REFRESH_SECRET: "y".repeat(16),
  };
  it("defaults to local", () => expect(loadConfig(base).AUTH_MODE).toBe("local"));
  it("requires the pool and client in cognito mode", () => {
    expect(() => loadConfig({ ...base, AUTH_MODE: "cognito" })).toThrow(/COGNITO_USER_POOL_ID/);
    expect(
      loadConfig({
        ...base,
        AUTH_MODE: "cognito",
        COGNITO_USER_POOL_ID: POOL,
        COGNITO_CLIENT_ID: CLIENT,
      }).AUTH_MODE,
    ).toBe("cognito");
  });
});
