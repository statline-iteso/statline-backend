import { Prisma, type PrismaClient } from "@prisma/client";
import { mockDeep, type DeepMockProxy } from "jest-mock-extended";
import { verifyPassword } from "../src/lib/auth";
import { ADMIN_EMAIL_DEFAULT, LIGAS, sembrar } from "../src/seed";

function p2002(): Prisma.PrismaClientKnownRequestError {
  return new Prisma.PrismaClientKnownRequestError("Unique constraint failed", {
    code: "P2002",
    clientVersion: "test",
  });
}

describe("sembrar", () => {
  let prisma: DeepMockProxy<PrismaClient>;
  beforeEach(() => {
    prisma = mockDeep<PrismaClient>();
  });

  it("upserts the three api-sports leagues without touching existing rows", async () => {
    const r = await sembrar(prisma, {});
    expect(r).toEqual({ ligas: 3, admin: null });
    expect(prisma.liga.upsert).toHaveBeenCalledTimes(LIGAS.length);
    const llamada = prisma.liga.upsert.mock.calls[0]![0];
    expect(llamada.update).toEqual({});
    expect(llamada.where).toEqual({
      proveedor_proveedorLigaId_temporada: {
        proveedor: "api-sports",
        proveedorLigaId: "12",
        temporada: "2025-2026",
      },
    });
    expect(prisma.usuario.upsert).not.toHaveBeenCalled();
  });

  it("creates the admin with a hashed password when SEED_ADMIN_PASSWORD is set", async () => {
    const r = await sembrar(prisma, { SEED_ADMIN_PASSWORD: "s3creto-largo" });
    expect(r.admin).toBe(ADMIN_EMAIL_DEFAULT);
    const llamada = prisma.usuario.upsert.mock.calls[0]![0];
    expect(llamada.where).toEqual({ email: ADMIN_EMAIL_DEFAULT });
    expect(llamada.update).toEqual({});
    expect(llamada.create.rol).toBe("ADMIN");
    expect(llamada.create.passwordHash).not.toBe("s3creto-largo");
    await expect(verifyPassword("s3creto-largo", llamada.create.passwordHash)).resolves.toBe(true);
  });

  it("uses SEED_ADMIN_EMAIL when given", async () => {
    const r = await sembrar(prisma, {
      SEED_ADMIN_PASSWORD: "x",
      SEED_ADMIN_EMAIL: "ops@statline.mx",
    });
    expect(r.admin).toBe("ops@statline.mx");
  });

  it("retries once when another pod inserted the same row first (P2002)", async () => {
    prisma.liga.upsert.mockRejectedValueOnce(p2002());
    await sembrar(prisma, {});
    expect(prisma.liga.upsert).toHaveBeenCalledTimes(LIGAS.length + 1);
  });

  it("fails on any other database error", async () => {
    prisma.liga.upsert.mockRejectedValueOnce(new Error("connection refused"));
    await expect(sembrar(prisma, {})).rejects.toThrow("connection refused");
  });
});
