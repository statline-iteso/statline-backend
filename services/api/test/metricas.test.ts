import { defaultSchemasDir } from "../src/config";
import { createMetricasValidator } from "../src/lib/metricas";

const validator = createMetricasValidator(defaultSchemasDir);

describe("createMetricasValidator", () => {
  it("accepts valid metrics for each sport", () => {
    expect(validator.validar("BASQUETBOL", { puntos: 20, rebotes: 5, asistencias: 3 })).toEqual([]);
    expect(validator.validar("FUTBOL", { goles: 1, asistencias: 0 })).toEqual([]);
    expect(
      validator.validar("AMERICANO", { pase: { completos: 10, intentos: 15, yardas: 120 } }),
    ).toEqual([]);
  });

  it("reports a missing required key at the metricas root", () => {
    const errores = validator.validar("BASQUETBOL", { puntos: 20, rebotes: 5 });
    expect(errores).toEqual([
      expect.objectContaining({
        path: "metricas",
        message: expect.stringContaining("asistencias"),
      }),
    ]);
  });

  it("reports a wrong value at its dotted path", () => {
    const errores = validator.validar("BASQUETBOL", { puntos: -1, rebotes: 5, asistencias: 3 });
    expect(errores).toEqual([expect.objectContaining({ path: "metricas.puntos" })]);
  });

  it("rejects keys that are not in the schema (additionalProperties false)", () => {
    const errores = validator.validar("FUTBOL", { goles: 1, asistencias: 0, xg: 0.4 });
    expect(errores).toEqual([expect.objectContaining({ path: "metricas.xg" })]);
  });

  it("applies the sport's own schema: NFL needs at least one group", () => {
    expect(validator.validar("AMERICANO", {})).not.toEqual([]);
    expect(validator.validar("BASQUETBOL", {})).not.toEqual([]);
  });

  it("validates nested NFL groups", () => {
    const errores = validator.validar("AMERICANO", {
      carrera: { acarreos: 3 },
    });
    expect(errores).toEqual([expect.objectContaining({ path: "metricas.carrera" })]);
  });

  it("fails at construction when a schema file is missing", () => {
    expect(() => createMetricasValidator("/no/such/schemas-dir")).toThrow(/ENOENT/);
  });
});
