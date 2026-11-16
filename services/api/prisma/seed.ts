/**
 * Seed: the three leagues (proposal §2.1, "Semilla más ingesta") and a local admin.
 * Run with `pnpm db:seed`. The admin password comes from SEED_ADMIN_PASSWORD; never commit it.
 */
import { PrismaClient } from "@prisma/client";
import { hashPassword } from "../src/lib/auth";

const prisma = new PrismaClient();
// API-Sports league ids: NBA = 12 (basketball), NFL = 1 (american-football), Liga MX = 262 (football).
// Seasons use each API's format and must match TEMPORADA_* in the ingesta ConfigMap.
const LIGAS = [
  {
    nombre: "NBA",
    deporte: "BASQUETBOL",
    pais: "USA",
    proveedorLigaId: "12",
    temporada: "2025-2026",
  },
  { nombre: "NFL", deporte: "AMERICANO", pais: "USA", proveedorLigaId: "1", temporada: "2026" },
  {
    nombre: "Liga MX",
    deporte: "FUTBOL",
    pais: "México",
    proveedorLigaId: "262",
    temporada: "2026",
  },
] as const;

async function main() {
  for (const liga of LIGAS) {
    await prisma.liga.upsert({
      where: {
        proveedor_proveedorLigaId_temporada: {
          proveedor: "api-sports",
          proveedorLigaId: liga.proveedorLigaId,
          temporada: liga.temporada,
        },
      },
      update: {},
      create: liga,
    });
  }

  const password = process.env.SEED_ADMIN_PASSWORD;
  if (password) {
    await prisma.usuario.upsert({
      where: { email: process.env.SEED_ADMIN_EMAIL ?? "admin@statline.local" },
      update: {},
      create: {
        email: process.env.SEED_ADMIN_EMAIL ?? "admin@statline.local",
        nombre: "Administrador",
        rol: "ADMIN",
        passwordHash: await hashPassword(password),
      },
    });
  }
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (err: unknown) => {
    process.stderr.write(`${String(err)}\n`);
    await prisma.$disconnect();
    process.exit(1);
  });
