import { Prisma, type PrismaClient } from "@prisma/client";

/*
 * JSONB aggregation for player averages and trends (SL-27). Every value from the request reaches
 * SQL as a bound parameter through Prisma's tagged templates. Metric paths come from the sport's
 * JSON Schema (never from the request except as a validated key), and are split on "." into a
 * text[] for #> / #>> so NFL groups ("pase.yardas") work.
 */

export interface PromediosJugador {
  partidos: number;
  minutosPromedio: number | null;
  /** One entry per numeric metric in the schema; null when no considered game recorded it. */
  promedios: Record<string, number | null>;
}

export interface PuntoTendencia {
  partidoId: string;
  fecha: Date;
  valor: number;
}

/** CTE `base` with the player's last games (all when `ultimos` is undefined), newest first. */
function partidosDelJugador(jugadorId: string, ultimos?: number): Prisma.Sql {
  const limite = ultimos === undefined ? Prisma.empty : Prisma.sql`LIMIT ${ultimos}`;
  return Prisma.sql`
    WITH base AS (
      SELECT e.metricas, e.minutos
      FROM estadistica_jugador_partido e
      JOIN partido p ON p.id = e.partido_id
      WHERE e.jugador_id = ${jugadorId}::uuid
      ORDER BY p.fecha DESC
      ${limite}
    )`;
}

export async function promediosJugador(
  prisma: PrismaClient,
  jugadorId: string,
  rutas: readonly string[],
  ultimos?: number,
): Promise<PromediosJugador> {
  const resumen = await prisma.$queryRaw<
    { partidos: number; minutosPromedio: number | null }[]
  >(Prisma.sql`
    ${partidosDelJugador(jugadorId, ultimos)}
    SELECT count(*)::int AS partidos, avg(minutos)::float8 AS "minutosPromedio" FROM base`);
  const fila = resumen?.[0];
  const partidos = fila?.partidos ?? 0;
  const minutosPromedio = fila?.minutosPromedio ?? null;
  if (partidos === 0 || rutas.length === 0) {
    return { partidos, minutosPromedio, promedios: {} };
  }

  const filas = await prisma.$queryRaw<{ metrica: string; promedio: number | null }[]>(Prisma.sql`
    ${partidosDelJugador(jugadorId, ultimos)},
    hojas AS (
      SELECT v.metrica, (b.metricas #>> string_to_array(v.metrica, '.'))::float8 AS valor
      FROM base b
      CROSS JOIN (VALUES ${Prisma.join(rutas.map((ruta) => Prisma.sql`(${ruta})`))}) AS v(metrica)
      WHERE jsonb_typeof(b.metricas #> string_to_array(v.metrica, '.')) = 'number'
    )
    SELECT metrica, avg(valor)::float8 AS promedio FROM hojas GROUP BY metrica`);

  const porMetrica = new Map((filas ?? []).map((f) => [f.metrica, f.promedio]));
  const promedios = Object.fromEntries(rutas.map((ruta) => [ruta, porMetrica.get(ruta) ?? null]));
  return { partidos, minutosPromedio, promedios };
}

/** Last `n` games where the player recorded `metrica`, oldest first (chart order). */
export async function tendenciaJugador(
  prisma: PrismaClient,
  jugadorId: string,
  metrica: string,
  n: number,
): Promise<PuntoTendencia[]> {
  const filas = await prisma.$queryRaw<PuntoTendencia[]>`
    SELECT e.partido_id AS "partidoId", p.fecha AS fecha,
           (e.metricas #>> string_to_array(${metrica}, '.'))::float8 AS valor
    FROM estadistica_jugador_partido e
    JOIN partido p ON p.id = e.partido_id
    WHERE e.jugador_id = ${jugadorId}::uuid
      AND jsonb_typeof(e.metricas #> string_to_array(${metrica}, '.')) = 'number'
    ORDER BY p.fecha DESC
    LIMIT ${n}`;
  return (filas ?? []).reverse();
}
