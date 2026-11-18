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
| D-15 | 2026-11-16 | Watchlists are owner-only; other users' lists are 404 (not 403); ADMIN reads all but writes only its own | Decided |
| D-16 | 2026-11-16 | `DELETE /api/listas/:id/elementos/:ref` takes the jugador/equipo id (`refId`), not the elemento id | Decided |
| D-17 | 2026-11-16 | Box-score sport comes from the partido's liga; metrics are validated by Ajv against the schema on every write and on batches (all-or-nothing) | Decided |
| D-18 | 2026-11-16 | JSON body limit 1 MB so a 500-line batch fits; larger bodies get 413 | Decided |
| D-15 | 2026-11-16 | Manual ingestion runs create a Job from the CronJob via the in-cluster API, behind `LanzadorIngesta` (`INGESTA_LANZADOR`, default disabled) | Decided |
| D-16 | 2026-11-16 | Alerts are owner-scoped; ADMIN may read and list all but change only its own; referenced jugador/equipo are validated | Decided |
| D-15 | 2026-11-16 | Liga MX (api-football, league 262) mapped from the provider documentation; unverified against a live response | Decided (limitation) |
| D-15 | 2026-11-16 | NFL adapter (api-american-football, league 1) built from API-Sports documentation, not from a live response | Decided (unverified) |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.

### D-05 · JSONB instead of tables per sport
Cross-sport queries (a player's lines, a game's box score) stay one table; sport-specific aggregation uses `(metricas->>'puntos')::int`. The engine doesn't validate JSONB shape, hence D-07 and strict schemas.

### D-15 · Redis optional and never fatal
Redis backs the catalog cache and the rate limiters (`rate-limit-redis`). Without `REDIS_URL` nothing connects. With it, every Redis error or timeout (250 ms per cache call) is logged and the request continues: a cache miss, or a count in the process's memory store. Only `/readyz` treats Redis as a dependency (503 when it does not answer PING).

### D-16 · Catalog cache invalidation by version counter
Standings, form and box scores depend on several resources, so per-resource invalidation would need a dependency map. Instead each key embeds one catalog version; a successful catalog write INCRs it and old keys expire by TTL. This needs no SCAN and cannot race a stale write into the new version. Trade-off: any catalog write invalidates all catalog cache entries, which is acceptable because writes are rare and ADMIN-only.
### D-15 · Manual ingestion through the Kubernetes API
The api creates a Job from `spec.jobTemplate` of the existing CronJob, so the sport's image, args and env stay defined once in infra. Trade-off: the api needs RBAC `create jobs` and `get cronjobs` in its namespace. The launcher is an interface and defaults to disabled (503) so local and test environments never touch a cluster. The https module is used instead of fetch because Node's fetch cannot take the cluster CA without undici, which is not a dependency. Not chosen: a Job runner inside the api (no isolation, one more process) and a queue (SL-31 scope).

### D-16 · Alert ownership
Alerts carry `usuarioId` from the JWT. Only ADMIN may list and read other users' alerts, for administration; changes are owner-only even for ADMIN. Referenced ids are checked in the api (400 with the field) because the DB only checks the FK, which would surface as a 500.
### D-15 · NFL field mapping from documentation (SL-18)
`AdaptadorAmericano` maps API-Sports american-football games and player statistics to `schemas/americano.schema.json`. No API key was available during development, so the fixtures in `tests/fixtures/nfl_*.json` follow the documented shapes and are **not** a recording. The assumptions to confirm on the first real run:
- Games nest under `game` (`id`, `status.short`, `date.timestamp`, UTC), unlike api-basketball; `scores.<side>.total` and `league.season` are top level.
- Player statistics come per team as `[{team, groups: [{name, players: [{player, statistics: [{name, value}]}]}]}]` with categories Passing, Rushing, Receiving, Defensive (or Defense) and Kicking; made/attempts values (`comp att`, `field goals`, `extra points`) are `"made/attempts"` strings. Exact stat names are the least certain part (aliases are accepted for a few).
- Game status codes (`NS`, `Q1`–`Q4`, `OT`, `HT`, `FT`, `AOT`, `PST`, `CANC`, …).
- The API reports no player position, so `jugador.posicion` stays empty.

Unknown stat names are ignored and unparsable values count as 0, so a wrong name shows up as zeros rather than a failed run. Check a real `/games/statistics/players` response before trusting NFL numbers.

### D-09 · Express 4 and CommonJS
The proposal says Express. Express 4 + `ts-jest` in CommonJS avoids ESM test configuration; async errors are forwarded with a small `ah()` wrapper.

### D-15 · Player aggregates in SQL over JSONB
`/promedios`, `/tendencia` and `/comparar` run `$queryRaw` tagged templates over `metricas`. The metric list comes from `schemas/<deporte>.schema.json` (read by the api at runtime, so the image copies `schemas/`), which also validates `?metrica=`. Only numeric leaves are averaged; a metric averages over the games that recorded it. Known limit: no index for `#>>` on the path, so large seasons may need materialized views (see future work).

## 3. Known limitations

- `/api/partidos?fecha=` filters a UTC day; a 9 pm Mexico game shows up on the next UTC date.
- Box-score field names from api-basketball were mapped from documentation and recorded fixtures; confirm against a live response once a key is available.
- Ingestion writes straight to PostgreSQL, bypassing the api, so catalog cache entries can be stale for up to `CACHE_TTL_S` (60 s) after an ingestion run.
- Rate limits are per client IP and behind one trusted proxy hop; a Redis outage makes the limit per replica instead of global.
- Liga MX (D-15): the api-football field mapping, the status codes and the `round` → `jornada` parsing come from the v3 documentation. The fixtures in `services/ingesta/tests/fixtures/ligamx_*.json` are synthetic, shaped like that documentation (player and club names are invented). Confirm the field names, that `passes.accuracy` is a count of accurate passes (stored as a percentage of `passes.total`), the string-typed `games.rating`, and the position values against a live response once a key is available.
- Liga MX metrics: a provider null on a required metric (`goles`, `asistencias`) is stored as 0, a null on an optional metric is left out of `metricas`. Squad players with null minutes (never on the pitch) are not stored.
- NFL field names are documentation-based (D-15) and `partido.jornada` stays empty because the provider's week labels are not a clean number.

## 4. Future work

- OpenAPI generated from the zod schemas (for Schemathesis contract tests, proposal §4.4).
- Testcontainers instead of the CI service container for integration tests.
- Materialized views for season averages if JSONB aggregation gets slow.

### D-15 to D-18 · SL-28 (estadísticas y listas)
- **Ownership.** `/api/listas` derives the owner from the JWT `sub`, never from the body. Non-owners get 404 so list ids can't be probed. ADMIN can read every list (for support) but cannot change lists it does not own; if moderation writes are needed later, that is a one-line change in `routes/listas.ts`.
- **Element reference.** Clients know the jugador or equipo id, not the element id, so `DELETE .../elementos/:ref` uses `refId`. Within one list `(tipo, refId)` is unique, and uuids of jugador and equipo never collide in practice.
- **Batch.** `POST /api/estadisticas/lote` is capped at 500 lines and runs in one transaction. Errors are reported per index in the same response, so the client can fix the lines and resend the whole batch.
- **Ajv.** Schemas are compiled once at boot (`ajv/dist/2020`, Draft 2020-12, `allErrors`), so a missing schema fails the start, not the first write. Ajv is pinned to 8.17.1 like the other dependencies.

