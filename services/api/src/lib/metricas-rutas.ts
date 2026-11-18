import { readFileSync } from "node:fs";
import path from "node:path";
import type { Deporte } from "@prisma/client";

/** Repo root: the same depth from src/lib (dev, tests) and dist/lib (build). */
const REPO_ROOT = path.resolve(__dirname, "../../../..");

type JsonObject = Record<string, unknown>;

const isObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function resolverRef(nodo: JsonObject, defs: JsonObject): JsonObject {
  const ref = nodo.$ref;
  if (typeof ref !== "string") return nodo;
  const destino = defs[ref.replace(/^#\/\$defs\//, "")];
  return isObject(destino) ? destino : {};
}

/**
 * Dotted paths of every numeric leaf of a metrics JSON Schema. Flat sports (NBA, Liga MX) give
 * "puntos"; NFL groups give "pase.yardas". Pure, so it is unit-tested without files.
 */
export function rutasNumericas(schema: unknown): string[] {
  if (!isObject(schema)) return [];
  const defs = isObject(schema.$defs) ? schema.$defs : {};
  const rutas: string[] = [];
  const recorrer = (nodo: JsonObject, prefijo: string) => {
    const propiedades = isObject(nodo.properties) ? nodo.properties : {};
    for (const [clave, crudo] of Object.entries(propiedades)) {
      if (!isObject(crudo)) continue;
      const sub = resolverRef(crudo, defs);
      const ruta = prefijo ? `${prefijo}.${clave}` : clave;
      if (sub.type === "integer" || sub.type === "number") rutas.push(ruta);
      else if (sub.type === "object") recorrer(sub, ruta);
    }
  };
  recorrer(schema, "");
  return rutas;
}

const cache = new Map<string, readonly string[]>();

/**
 * Numeric metric paths for a sport, read from `<schemasDir>/<deporte>.schema.json` (same file
 * name rule as the ingesta validator). `schemasDir` is relative to the repo root unless absolute.
 * Results are cached per file. The file is trusted (it ships with the image), so a missing file
 * is a server error, not a client one.
 */
export function metricasNumericas(deporte: Deporte, schemasDir = "schemas"): readonly string[] {
  const archivo = path.resolve(REPO_ROOT, schemasDir, `${deporte.toLowerCase()}.schema.json`);
  let rutas = cache.get(archivo);
  if (!rutas) {
    rutas = rutasNumericas(JSON.parse(readFileSync(archivo, "utf8")) as unknown);
    cache.set(archivo, rutas);
  }
  return rutas;
}
