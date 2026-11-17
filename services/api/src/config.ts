import path from "node:path";
import { z } from "zod";

/** Repo `schemas/` when running from source (src/ or dist/ are both three levels below the root). */
export const defaultSchemasDir = path.resolve(__dirname, "../../../schemas");

const ConfigSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().positive().default(3000),
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(16),
  JWT_REFRESH_SECRET: z.string().min(16),
  JWT_ACCESS_TTL: z.string().default("15m"),
  JWT_REFRESH_TTL: z.string().default("7d"),
  PREDICCIONES_URL: z.string().url().default("http://predicciones:8000"),
  /** Optional. When unset the cache is bypassed and rate limits are kept in process memory. */
  REDIS_URL: z.string().optional(),
  CACHE_TTL_S: z.coerce.number().int().positive().default(60),
  RATE_LIMIT_PER_MIN: z.coerce.number().int().positive().default(300),
  RATE_LIMIT_LOGIN_PER_MIN: z.coerce.number().int().positive().default(10),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"]).default("info"),
  /** Directory with <deporte>.schema.json files. The image sets /app/schemas. */
  SCHEMAS_DIR: z.string().min(1).default(defaultSchemasDir),
});

export type Config = z.infer<typeof ConfigSchema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  return ConfigSchema.parse(env);
}
