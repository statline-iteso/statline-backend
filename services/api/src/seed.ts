/**
 * Seed: the three leagues (proposal §2.1, "Semilla más ingesta") and an admin.
 *
 * Local: `pnpm db:seed`. In the cluster the api image runs `node dist/seed.js` as an initContainer
 * after `prisma migrate deploy`, so every fresh database gets the leagues the ingesta CronJobs look
 * up. The admin password comes from SEED_ADMIN_PASSWORD (Key Vault `seed-admin-password` in AKS);
 * never commit it. Every write is an upsert that leaves existing rows alone, so it is safe on every
 * pod start.
 */
import { Prisma, PrismaClient } from "@prisma/client";
import { hashPassword } from "./lib/auth";

// API-Sports league ids: NBA = 12 (basketball), NFL = 1 (american-football), Liga MX = 262 (football).
// Seasons use each API's format and must match TEMPORADA_* in the ingesta ConfigMap.
export const LIGAS = [
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

export const ADMIN_EMAIL_DEFAULT = "admin@statline.local";

/**
 * Two api pods starting together can race on the same upsert: one inserts, the other gets a
 * unique violation (P2002). The row then exists, which is all the seed wants, so it retries once.
 */
async function upsertTolerante(upsert: () => Promise<unknown>): Promise<void> {
  try {
    await upsert();
  } catch (err) {
    if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2002") {
      await upsert();
      return;
    }
    throw err;
  }
}

export interface ResultadoSemilla {
  ligas: number;
  admin: string | null;
}

export async function sembrar(
  prisma: PrismaClient,
  env: Record<string, string | undefined> = process.env,
): Promise<ResultadoSemilla> {
  for (const liga of LIGAS) {
    await upsertTolerante(() =>
      prisma.liga.upsert({
        where: {
          proveedor_proveedorLigaId_temporada: {
            proveedor: "api-sports",
            proveedorLigaId: liga.proveedorLigaId,
            temporada: liga.temporada,
          },
        },
        update: {},
        create: liga,
      }),
    );
  }

  const password = env.SEED_ADMIN_PASSWORD;
  if (!password) return { ligas: LIGAS.length, admin: null };
  const email = env.SEED_ADMIN_EMAIL || ADMIN_EMAIL_DEFAULT;
  const passwordHash = await hashPassword(password);
  await upsertTolerante(() =>
    prisma.usuario.upsert({
      where: { email },
      update: {},
      create: { email, nombre: "Administrador", rol: "ADMIN", passwordHash },
    }),
  );
  return { ligas: LIGAS.length, admin: email };
}

/* istanbul ignore next -- process entry point; sembrar() is what the tests cover */
if (require.main === module) {
  const prisma = new PrismaClient();
  sembrar(prisma)
    .then(async (r) => {
      process.stdout.write(
        `seed: ${r.ligas} ligas${r.admin ? `, admin ${r.admin}` : ", no admin (SEED_ADMIN_PASSWORD unset)"}\n`,
      );
      await prisma.$disconnect();
    })
    .catch(async (err: unknown) => {
      process.stderr.write(`seed failed: ${String(err)}\n`);
      await prisma.$disconnect();
      process.exit(1);
    });
}
