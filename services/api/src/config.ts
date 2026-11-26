import path from "node:path";
import { z } from "zod";

/** Repo `schemas/` when running from source (src/ or dist/ are both three levels below the root). */
export const defaultSchemasDir = path.resolve(__dirname, "../../../schemas");

const ConfigSchema = z
  .object({
    NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
    PORT: z.coerce.number().int().positive().default(3000),
    DATABASE_URL: z.string().url(),
    JWT_SECRET: z.string().min(16),
    JWT_REFRESH_SECRET: z.string().min(16),
    JWT_ACCESS_TTL: z.string().default("15m"),
    JWT_REFRESH_TTL: z.string().default("7d"),
    PREDICCIONES_URL: z.string().url().default("http://predicciones:8000"),
    PREDICCIONES_TIMEOUT_MS: z.coerce.number().int().positive().default(30_000),
    /** Optional. When unset the cache is bypassed and rate limits are kept in process memory. */
    REDIS_URL: z.string().optional(),
    CACHE_TTL_S: z.coerce.number().int().positive().default(60),
    RATE_LIMIT_PER_MIN: z.coerce.number().int().positive().default(300),
    RATE_LIMIT_LOGIN_PER_MIN: z.coerce.number().int().positive().default(10),
    /** deshabilitado (default): POST /api/ingestas/ejecutar answers 503. kubernetes: creates a Job. */
    INGESTA_LANZADOR: z.enum(["deshabilitado", "kubernetes"]).default("deshabilitado"),
    // Prefix of the ingesta CronJob names; the Helm chart names them `<release>-ingesta-<deporte>`.
    INGESTA_CRONJOB_PREFIJO: z.string().default(""),
    LOG_LEVEL: z
      .enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"])
      .default("info"),
    /** Directory with <deporte>.schema.json files. The image sets /app/schemas. */
    SCHEMAS_DIR: z.string().min(1).default(defaultSchemasDir),
    /** local (default): our own login and JWTs. cognito: Cognito ID tokens (infra D-47). */
    AUTH_MODE: z.enum(["local", "cognito"]).default("local"),
    COGNITO_REGION: z.string().default("us-east-1"),
    COGNITO_USER_POOL_ID: z.string().optional(),
    COGNITO_CLIENT_ID: z.string().optional(),
  })
  .superRefine((c, ctx) => {
    if (c.AUTH_MODE !== "cognito") return;
    for (const key of ["COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"] as const) {
      if (!c[key])
        ctx.addIssue({ code: "custom", path: [key], message: "required when AUTH_MODE=cognito" });
    }
  });

export type Config = z.infer<typeof ConfigSchema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  return ConfigSchema.parse(env);
}
