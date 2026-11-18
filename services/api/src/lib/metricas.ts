import fs from "node:fs";
import path from "node:path";
import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020";
import type { Deporte } from "@prisma/client";

/** One problem with a `metricas` object; `path` is dotted, e.g. "metricas.puntos". */
export interface ErrorMetrica {
  path: string;
  message: string;
}

export interface MetricasValidator {
  /** Returns [] when valid. Never throws for bad data; only for a missing or broken schema file. */
  validar(deporte: Deporte, metricas: unknown): ErrorMetrica[];
}

const ARCHIVO: Record<Deporte, string> = {
  BASQUETBOL: "basquetbol",
  AMERICANO: "americano",
  FUTBOL: "futbol",
};

/**
 * Loads schemas/<deporte>.schema.json (Draft 2020-12) once at startup, so a missing schema
 * fails the boot instead of the first request. Same rule as the ingesta service (D-06).
 */
export function createMetricasValidator(schemasDir: string): MetricasValidator {
  const ajv = new Ajv2020({ allErrors: true });
  const validadores = new Map<Deporte, ValidateFunction>();
  for (const deporte of Object.keys(ARCHIVO) as Deporte[]) {
    const ruta = path.join(schemasDir, `${ARCHIVO[deporte]}.schema.json`);
    const esquema: unknown = JSON.parse(fs.readFileSync(ruta, "utf8"));
    validadores.set(deporte, ajv.compile(esquema as object));
  }

  return {
    validar(deporte, metricas) {
      const validate = validadores.get(deporte);
      if (!validate) throw new Error(`Sin esquema para ${deporte}`);
      if (validate(metricas)) return [];
      return (validate.errors ?? []).map(toErrorMetrica);
    },
  };
}

function toErrorMetrica(e: ErrorObject): ErrorMetrica {
  // additionalProperties reports the offending key in params, not in instancePath.
  const extra =
    e.keyword === "additionalProperties" ? `/${String(e.params.additionalProperty)}` : "";
  return {
    path: `metricas${e.instancePath}${extra}`.replace(/\//g, "."),
    message: e.message ?? "no es válido",
  };
}
