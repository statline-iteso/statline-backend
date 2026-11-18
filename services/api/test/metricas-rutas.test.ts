import { mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { metricasNumericas, rutasNumericas } from "../src/lib/metricas-rutas";

describe("rutasNumericas", () => {
  it("lists integer and number leaves of a flat schema, skipping strings", () => {
    expect(
      rutasNumericas({
        type: "object",
        properties: {
          goles: { type: "integer" },
          calificacion: { type: "number" },
          nota: { type: "string" },
        },
      }),
    ).toEqual(["goles", "calificacion"]);
  });

  it("descends into object groups and resolves $defs references (NFL)", () => {
    const schema = {
      $defs: { noNegativo: { type: "integer", minimum: 0 } },
      properties: {
        pase: {
          type: "object",
          properties: { yardas: { type: "integer" }, completos: { $ref: "#/$defs/noNegativo" } },
        },
        carrera: { type: "object", properties: { acarreos: { $ref: "#/$defs/noNegativo" } } },
      },
    };
    expect(rutasNumericas(schema)).toEqual(["pase.yardas", "pase.completos", "carrera.acarreos"]);
  });

  it("ignores unresolvable refs and non-object input", () => {
    expect(rutasNumericas({ properties: { x: { $ref: "#/$defs/missing" }, y: 5 } })).toEqual([]);
    expect(rutasNumericas(null)).toEqual([]);
    expect(rutasNumericas("schema")).toEqual([]);
  });
});

describe("metricasNumericas", () => {
  it("reads the sport's schema file from the repo by default", () => {
    expect(metricasNumericas("BASQUETBOL")).toContain("puntos");
    expect(metricasNumericas("AMERICANO")).toContain("pase.yardas");
  });

  it("reads from a custom directory and caches per file", () => {
    const dir = mkdtempSync(path.join(os.tmpdir(), "statline-schemas-"));
    writeFileSync(
      path.join(dir, "futbol.schema.json"),
      JSON.stringify({ properties: { goles: { type: "integer" } } }),
    );
    expect(metricasNumericas("FUTBOL", dir)).toEqual(["goles"]);
    expect(metricasNumericas("FUTBOL", dir)).toEqual(["goles"]);
  });

  it("throws when the schema file is missing", () => {
    expect(() => metricasNumericas("FUTBOL", "/no/such/dir")).toThrow();
  });
});
