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
| D-15 | 2026-11-16 | Model artifacts stored as bytea in `modelo_artefacto`, referenced as `db://<id>` | Decided |
| D-16 | 2026-11-16 | Synthetic demo data via `ingesta seed-demo` (provider `demo`, `demo-` ids), opt-in with `--confirmar`, never in CronJobs | Decided |
| D-17 | 2026-11-16 | Models are validated on a date-based holdout (last 20 %) and the stored bundle is fitted on the training part only | Decided |
| D-18 | 2026-11-16 | Activation rule: a candidate is activated only if it beats its baseline and is no worse than the active model on the same metric | Decided |
| D-19 | 2026-11-16 | Feature and target choices of the first models (windows of 10, NBA/NFL ties dropped, NFL targets by group) | Decided |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.

### D-15 · Model artifacts in PostgreSQL
Each trained model is serialized with joblib and stored in `modelo_artefacto.contenido` (BYTEA, with `sha256` and size). `modelo_prediccion.artefacto_uri` is `db://<modelo_artefacto.id>`. Predicciones replicas load the same bytes from the database, so no shared volume (PVC) is needed to keep them in sync, and a rollback is a change of the active row. Trade-off: artifacts are small (scikit-learn linear and tree models, well under a few MB) and the database is the only shared state; if models grow, move the bytes to object storage and keep the `db://` scheme for the old rows.

### D-16 · Synthetic demo data
`ingesta seed-demo` generates deterministic data (`random.Random(semilla)`) with the same normalized records the adapters return, validates every metrics line against the JSON Schemas and writes through `RepositorioPostgres`. It exists so the predictions work and the frontend can be developed without a live API-Sports quota. It requires `--confirmar`, records an `ejecucion_ingesta` row with proveedor `demo`, and is referenced by no CronJob.

### D-17 · Holdout and what gets stored
Train on the first 80 % of distinct dates, validate on the rest. The cut falls between dates, so a game never appears on both sides. The artifact is the model fitted on the training part, so the stored `metrica_error` describes exactly the bytes in `modelo_artefacto`. Trade-off: the last 20 % of games do not feed the stored model; a later version can refit on all data and keep the holdout metric as a validation record.

### D-18 · Activation rule
A new version is activated only when its metric is strictly better than its baseline (log-loss below the class priors; MAE below the rolling average). If another version is already active for the same (deporte, tipo), the candidate must also be no worse than it (`metrica <= metrica_error` of the active row). Both metrics are on the same name, so the comparison is valid, although each holdout covers a different period. Activation is one transaction that locks the group. A candidate that does not beat its baseline is never activated, even when nothing is active: the endpoint then reports that there is no active model.

### D-19 · First model choices
- Team windows of 10 games; rest days capped at 14. Each season is a separate `liga` row with its own teams, so history does not cross seasons (a season start has no history, imputed).
- NBA and NFL outcomes are `L`/`V`: tied games are dropped from training and from the holdout. Futbol keeps `E`.
- NFL player targets are the `yardas` of the passing, rushing and receiving groups. A row without that group is not a training row for that target.
- Gradient boosting: 200 trees, depth 3, learning rate 0.05, subsample 0.8, fixed seed.
- Artifacts are pickles (joblib). Load only bytes that this service wrote to the database; a compromised database would mean code execution in the predicciones pod.

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
