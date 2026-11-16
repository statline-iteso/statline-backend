/** Pure standings and form logic, no I/O (unit-tested in test/standings.test.ts). */

export interface ResultadoPartido {
  localId: string;
  visitaId: string;
  marcadorLocal: number;
  marcadorVisita: number;
}

export interface FilaPosicion {
  equipoId: string;
  jugados: number;
  ganados: number;
  empatados: number;
  perdidos: number;
  aFavor: number;
  enContra: number;
  diferencia: number;
  /** Fútbol: 3/1/0. NBA and NFL rank by win percentage, so this holds wins. */
  puntos: number;
  porcentaje: number;
}

export type Deporte = "BASQUETBOL" | "AMERICANO" | "FUTBOL";

export function calcularPosiciones(
  deporte: Deporte,
  equipoIds: string[],
  partidos: ResultadoPartido[],
): FilaPosicion[] {
  const filas = new Map<string, FilaPosicion>(
    equipoIds.map((equipoId) => [
      equipoId,
      {
        equipoId,
        jugados: 0,
        ganados: 0,
        empatados: 0,
        perdidos: 0,
        aFavor: 0,
        enContra: 0,
        diferencia: 0,
        puntos: 0,
        porcentaje: 0,
      },
    ]),
  );

  const anotar = (equipoId: string, favor: number, contra: number) => {
    const f = filas.get(equipoId);
    if (!f) return;
    f.jugados += 1;
    f.aFavor += favor;
    f.enContra += contra;
    if (favor > contra) f.ganados += 1;
    else if (favor === contra) f.empatados += 1;
    else f.perdidos += 1;
  };

  for (const p of partidos) {
    anotar(p.localId, p.marcadorLocal, p.marcadorVisita);
    anotar(p.visitaId, p.marcadorVisita, p.marcadorLocal);
  }

  for (const f of filas.values()) {
    f.diferencia = f.aFavor - f.enContra;
    f.puntos = deporte === "FUTBOL" ? f.ganados * 3 + f.empatados : f.ganados;
    // NFL counts a tie as half a win.
    f.porcentaje = f.jugados === 0 ? 0 : round3((f.ganados + f.empatados / 2) / f.jugados);
  }

  const orden = [...filas.values()];
  orden.sort((a, b) =>
    deporte === "FUTBOL"
      ? b.puntos - a.puntos || b.diferencia - a.diferencia || b.aFavor - a.aFavor
      : b.porcentaje - a.porcentaje || b.diferencia - a.diferencia,
  );
  return orden;
}

/**
 * Recent form for one team: "G" (ganado), "E" (empate), "P" (perdido), oldest first.
 * `partidos` must be sorted by date, newest first; only the first `n` are used.
 */
export function calcularForma(equipoId: string, partidos: ResultadoPartido[], n = 5): string {
  return partidos
    .slice(0, n)
    .map((p) => {
      const esLocal = p.localId === equipoId;
      const favor = esLocal ? p.marcadorLocal : p.marcadorVisita;
      const contra = esLocal ? p.marcadorVisita : p.marcadorLocal;
      return favor > contra ? "G" : favor === contra ? "E" : "P";
    })
    .reverse()
    .join("");
}

const round3 = (x: number) => Math.round(x * 1000) / 1000;
