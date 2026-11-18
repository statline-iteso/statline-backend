# Decisions, Limitations and Future Work

Add a new entry whenever something is decided; don't rewrite history. Replaced decisions are marked **Superseded by D-xx**.

## 1. Decision log

| ID | Date | Decision | Status |
|---|---|---|---|
| D-01 | 2026-11-16 | One repo for the three backend services (pnpm workspace + uv projects) | Decided |
| D-02 | 2026-11-16 | Prisma Migrate owns the schema; Python writes the same tables with SQL | Decided |
| D-03 | 2026-11-16 | snake_case tables/columns via `@@map`/`@map` | Decided |
| D-04 | 2026-11-16 | Client-generated UUIDs (no DB defaults) | Decided |
| D-05 | 2026-11-16 | Hybrid storage: common columns + `metricas` JSONB with GIN `jsonb_path_ops` | Decided |
| D-06 | 2026-11-16 | JSON Schemas live in `schemas/` at the repo root and are copied into the ingesta image | Decided |
| D-07 | 2026-11-16 | Invalid box-score lines are skipped and counted, not fatal for the run | Decided |
| D-08 | 2026-11-16 | Request budget per run (95) below the free plan's ~100/day | Decided |
| D-09 | 2026-11-16 | Express 4 + CommonJS for the api (Jest without ESM friction) | Decided |
| D-10 | 2026-11-16 | Generic `createCrudRouter` for the standard operations; extras registered first | Decided |
| D-11 | 2026-11-16 | Separate access/refresh secrets; refresh re-reads the role | Decided |
| D-12 | 2026-11-16 | Catalog writes are ADMIN-only; ingestion is the normal writer | Decided |
| D-13 | 2026-11-16 | Prisma CLI is a runtime dependency (initContainer runs `migrate deploy`) | Decided |
| D-14 | 2026-11-16 | Pending predicciones routes answer 501 with the issue id | Decided (temporary) |
| D-15 | 2026-11-16 | Redis is optional: cache bypass and in-memory rate limits without it, memory fallback on Redis errors | Decided |
| D-16 | 2026-11-16 | Catalog cache invalidated by one catalog-wide version counter, not per-resource prefixes or SCAN | Decided |
| D-15 | 2026-11-16 | Player aggregates computed in SQL over JSONB; metric keys come from the sport schema (`SCHEMAS_DIR`), NFL groups as dotted paths | Decided |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.

### D-05 · JSONB instead of tables per sport
Cross-sport queries (a player's lines, a game's box score) stay one table; sport-specific aggregation uses `(metricas->>'puntos')::int`. The engine doesn't validate JSONB shape, hence D-07 and strict schemas.

### D-15 · Redis optional and never fatal
Redis backs the catalog cache and the rate limiters (`rate-limit-redis`). Without `REDIS_URL` nothing connects. With it, every Redis error or timeout (250 ms per cache call) is logged and the request continues: a cache miss, or a count in the process's memory store. Only `/readyz` treats Redis as a dependency (503 when it does not answer PING).

### D-16 · Catalog cache invalidation by version counter
Standings, form and box scores depend on several resources, so per-resource invalidation would need a dependency map. Instead each key embeds one catalog version; a successful catalog write INCRs it and old keys expire by TTL. This needs no SCAN and cannot race a stale write into the new version. Trade-off: any catalog write invalidates all catalog cache entries, which is acceptable because writes are rare and ADMIN-only.

### D-09 · Express 4 and CommonJS
The proposal says Express. Express 4 + `ts-jest` in CommonJS avoids ESM test configuration; async errors are forwarded with a small `ah()` wrapper.

### D-15 · Player aggregates in SQL over JSONB
`/promedios`, `/tendencia` and `/comparar` run `$queryRaw` tagged templates over `metricas`. The metric list comes from `schemas/<deporte>.schema.json` (read by the api at runtime, so the image copies `schemas/`), which also validates `?metrica=`. Only numeric leaves are averaged; a metric averages over the games that recorded it. Known limit: no index for `#>>` on the path, so large seasons may need materialized views (see future work).

## 3. Known limitations

- `/api/partidos?fecha=` filters a UTC day; a 9 pm Mexico game shows up on the next UTC date.
- Box-score field names from api-basketball were mapped from documentation and recorded fixtures; confirm against a live response once a key is available.
- Ingestion writes straight to PostgreSQL, bypassing the api, so catalog cache entries can be stale for up to `CACHE_TTL_S` (60 s) after an ingestion run.
- Rate limits are per client IP and behind one trusted proxy hop; a Redis outage makes the limit per replica instead of global.

## 4. Future work

- OpenAPI generated from the zod schemas (for Schemathesis contract tests, proposal §4.4).
- Testcontainers instead of the CI service container for integration tests.
- Materialized views for season averages if JSONB aggregation gets slow.
