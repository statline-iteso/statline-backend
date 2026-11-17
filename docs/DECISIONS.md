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
| D-15 | 2026-11-16 | Watchlists are owner-only; other users' lists are 404 (not 403); ADMIN reads all but writes only its own | Decided |
| D-16 | 2026-11-16 | `DELETE /api/listas/:id/elementos/:ref` takes the jugador/equipo id (`refId`), not the elemento id | Decided |
| D-17 | 2026-11-16 | Box-score sport comes from the partido's liga; metrics are validated by Ajv against the schema on every write and on batches (all-or-nothing) | Decided |
| D-18 | 2026-11-16 | JSON body limit 1 MB so a 500-line batch fits; larger bodies get 413 | Decided |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.

### D-05 · JSONB instead of tables per sport
Cross-sport queries (a player's lines, a game's box score) stay one table; sport-specific aggregation uses `(metricas->>'puntos')::int`. The engine doesn't validate JSONB shape, hence D-07 and strict schemas.

### D-09 · Express 4 and CommonJS
The proposal says Express. Express 4 + `ts-jest` in CommonJS avoids ESM test configuration; async errors are forwarded with a small `ah()` wrapper.

## 3. Known limitations

- `/api/partidos?fecha=` filters a UTC day; a 9 pm Mexico game shows up on the next UTC date.
- Box-score field names from api-basketball were mapped from documentation and recorded fixtures; confirm against a live response once a key is available.
- No rate limiting until SL-31.

## 4. Future work

- OpenAPI generated from the zod schemas (for Schemathesis contract tests, proposal §4.4).
- Testcontainers instead of the CI service container for integration tests.
- Materialized views for season averages if JSONB aggregation gets slow.

### D-15 to D-18 · SL-28 (estadísticas y listas)
- **Ownership.** `/api/listas` derives the owner from the JWT `sub`, never from the body. Non-owners get 404 so list ids can't be probed. ADMIN can read every list (for support) but cannot change lists it does not own; if moderation writes are needed later, that is a one-line change in `routes/listas.ts`.
- **Element reference.** Clients know the jugador or equipo id, not the element id, so `DELETE .../elementos/:ref` uses `refId`. Within one list `(tipo, refId)` is unique, and uuids of jugador and equipo never collide in practice.
- **Batch.** `POST /api/estadisticas/lote` is capped at 500 lines and runs in one transaction. Errors are reported per index in the same response, so the client can fix the lines and resend the whole batch.
- **Ajv.** Schemas are compiled once at boot (`ajv/dist/2020`, Draft 2020-12, `allErrors`), so a missing schema fails the start, not the first write. Ajv is pinned to 8.17.1 like the other dependencies.

