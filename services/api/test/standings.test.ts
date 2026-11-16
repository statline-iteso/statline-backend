import { calcularForma, calcularPosiciones } from "../src/lib/standings";

const p = (localId: string, visitaId: string, marcadorLocal: number, marcadorVisita: number) => ({
  localId,
  visitaId,
  marcadorLocal,
  marcadorVisita,
});

describe("calcularPosiciones", () => {
  it("uses 3/1/0 points and goal difference for fútbol", () => {
    const tabla = calcularPosiciones(
      "FUTBOL",
      ["A", "B", "C"],
      [p("A", "B", 2, 0), p("B", "C", 1, 1), p("C", "A", 0, 0)],
    );
    expect(tabla.map((f) => f.equipoId)).toEqual(["A", "C", "B"]);
    expect(tabla[0]).toMatchObject({
      jugados: 2,
      ganados: 1,
      empatados: 1,
      puntos: 4,
      diferencia: 2,
    });
    expect(tabla[2]).toMatchObject({ perdidos: 1, puntos: 1, diferencia: -2 });
  });

  it("ranks NBA by win percentage", () => {
    const tabla = calcularPosiciones(
      "BASQUETBOL",
      ["A", "B"],
      [p("A", "B", 100, 90), p("B", "A", 101, 99), p("A", "B", 110, 100)],
    );
    expect(tabla[0]).toMatchObject({ equipoId: "A", ganados: 2, porcentaje: 0.667 });
  });

  it("counts an NFL tie as half a win", () => {
    const [a] = calcularPosiciones("AMERICANO", ["A", "B"], [p("A", "B", 17, 17)]);
    expect(a!.porcentaje).toBe(0.5);
  });

  it("includes teams with no games and ignores unknown teams", () => {
    const tabla = calcularPosiciones("FUTBOL", ["A"], [p("X", "Y", 1, 0)]);
    expect(tabla).toEqual([expect.objectContaining({ equipoId: "A", jugados: 0, porcentaje: 0 })]);
  });
});

describe("calcularForma", () => {
  it("returns the last n results oldest first", () => {
    // newest first
    const partidos = [p("A", "B", 1, 0), p("C", "A", 2, 2), p("A", "D", 0, 3)];
    expect(calcularForma("A", partidos)).toBe("PEG");
    expect(calcularForma("A", partidos, 2)).toBe("EG");
  });
});
