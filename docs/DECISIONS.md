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
| D-14 | 2026-11-16 | Pending predicciones routes answer 501 with the issue id | Superseded by D-33 (SL-37) |
| D-15 | 2026-11-16 | Redis is optional: cache bypass and in-memory rate limits without it, memory fallback on Redis errors | Decided |
| D-16 | 2026-11-16 | Catalog cache invalidated by one catalog-wide version counter, not per-resource prefixes or SCAN | Decided |
| D-17 | 2026-11-16 | Player aggregates computed in SQL over JSONB; metric keys come from the sport schema (`SCHEMAS_DIR`), NFL groups as dotted paths | Decided |
| D-18 | 2026-11-16 | Watchlists are owner-only; other users' lists are 404 (not 403); ADMIN reads all but writes only its own | Decided |
| D-19 | 2026-11-16 | `DELETE /api/listas/:id/elementos/:ref` takes the jugador/equipo id (`refId`), not the elemento id | Decided |
| D-20 | 2026-11-16 | Box-score sport comes from the partido's liga; metrics are validated by Ajv against the schema on every write and on batches (all-or-nothing) | Decided |
| D-21 | 2026-11-16 | JSON body limit 1 MB so a 500-line batch fits; larger bodies get 413 | Decided |
| D-22 | 2026-11-16 | Manual ingestion runs create a Job from the CronJob via the in-cluster API, behind `LanzadorIngesta` (`INGESTA_LANZADOR`, default disabled) | Decided |
| D-23 | 2026-11-16 | Alerts are owner-scoped; ADMIN may read and list all but change only its own; referenced jugador/equipo are validated | Decided |
| D-24 | 2026-11-16 | NFL adapter (api-american-football, league 1) built from API-Sports documentation, not from a live response | Decided (unverified) |
| D-25 | 2026-11-16 | Liga MX (api-football, league 262) mapped from the provider documentation; unverified against a live response | Decided (limitation) |
| D-26 | 2026-11-16 | Fallback providers (balldontlie for NBA, TheSportsDB for NFL and Liga MX) take over for the rest of a run when API-Sports is out of quota or down; duplicates across providers are not merged | Decided (limitation) |
| D-27 | 2026-11-16 | balldontlie and TheSportsDB mappings built from their documentation, not from live responses | Decided (unverified) |
| D-28 | 2026-11-16 | Model artifacts stored as bytea in `modelo_artefacto`, referenced as `db://<id>` | Decided |
| D-29 | 2026-11-16 | Synthetic demo data via `ingesta seed-demo` (provider `demo`, `demo-` ids), opt-in with `--confirmar`, never in CronJobs | Decided |
| D-30 | 2026-11-16 | Models are validated on a date-based holdout (last 20 %) and the stored bundle is fitted on the training part only | Decided |
| D-31 | 2026-11-16 | Activation rule: a candidate is activated only if it beats its baseline and is no worse than the active model on the same metric | Decided |
| D-32 | 2026-11-16 | Feature and target choices of the first models (windows of 10, NBA/NFL ties dropped, NFL targets by group) | Decided |
| D-33 | 2026-11-16 | Prediction endpoints are synchronous; one autocommit connection per request; forecasts and projections are replaced per (game or player, game, model) | Decided |
| D-34 | 2026-11-16 | predicciones responses are camelCase, requests snake_case; projection `metricas` is a flat object with dotted NFL keys | Decided |
| D-35 | 2026-11-16 | `POST /modelos/{id}/activar` is an admin override that bypasses the D-31 baseline rule | Decided |
| D-36 | 2026-11-17 | Demo data carries a strong team-strength signal and defaults to 240 days, so every model trained on it can beat its baseline | Decided |
| D-37 | 2026-11-19 | The seed ships in the api image (`dist/seed.js`) and runs as a second initContainer after the migrations, so a fresh cluster database gets its leagues and first ADMIN without dev tools | Decided |
| D-38 | 2026-11-23 | An API-Sports plan error (`errors.plan`, the free plan's season and date limits) is a `PlanSinAccesoError` and switches the run to the fallback, like an outage | Decided |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.


### D-05 · JSONB instead of tables per sport
Cross-sport queries (a player's lines, a game's box score) stay one table; sport-specific aggregation uses `(metricas->>'puntos')::int`. The engine doesn't validate JSONB shape, hence D-07 and strict schemas.


### D-09 · Express 4 and CommonJS
The proposal says Express. Express 4 + `ts-jest` in CommonJS avoids ESM test configuration; async errors are forwarded with a small `ah()` wrapper.


### D-15 · Redis optional and never fatal
Redis backs the catalog cache and the rate limiters (`rate-limit-redis`). Without `REDIS_URL` nothing connects. With it, every Redis error or timeout (250 ms per cache call) is logged and the request continues: a cache miss, or a count in the process's memory store. Only `/readyz` treats Redis as a dependency (503 when it does not answer PING).


### D-16 · Catalog cache invalidation by version counter
Standings, form and box scores depend on several resources, so per-resource invalidation would need a dependency map. Instead each key embeds one catalog version; a successful catalog write INCRs it and old keys expire by TTL. This needs no SCAN and cannot race a stale write into the new version. Trade-off: any catalog write invalidates all catalog cache entries, which is acceptable because writes are rare and ADMIN-only.

### D-17 · Player aggregates in SQL over JSONB
`/promedios`, `/tendencia` and `/comparar` run `$queryRaw` tagged templates over `metricas`. The metric list comes from `schemas/<deporte>.schema.json` (read by the api at runtime, so the image copies `schemas/`), which also validates `?metrica=`. Only numeric leaves are averaged; a metric averages over the games that recorded it. Known limit: no index for `#>>` on the path, so large seasons may need materialized views (see future work).

### D-18 to D-21 · SL-28 (estadísticas y listas)
- **Ownership.** `/api/listas` derives the owner from the JWT `sub`, never from the body. Non-owners get 404 so list ids can't be probed. ADMIN can read every list (for support) but cannot change lists it does not own; if moderation writes are needed later, that is a one-line change in `routes/listas.ts`.
- **Element reference.** Clients know the jugador or equipo id, not the element id, so `DELETE .../elementos/:ref` uses `refId`. Within one list `(tipo, refId)` is unique, and uuids of jugador and equipo never collide in practice.
- **Batch.** `POST /api/estadisticas/lote` is capped at 500 lines and runs in one transaction. Errors are reported per index in the same response, so the client can fix the lines and resend the whole batch.
- **Ajv.** Schemas are compiled once at boot (`ajv/dist/2020`, Draft 2020-12, `allErrors`), so a missing schema fails the start, not the first write. Ajv is pinned to 8.17.1 like the other dependencies.

### D-22 · Manual ingestion through the Kubernetes API
The api creates a Job from `spec.jobTemplate` of the existing CronJob, so the sport's image, args and env stay defined once in infra. Trade-off: the api needs RBAC `create jobs` and `get cronjobs` in its namespace. The launcher is an interface and defaults to disabled (503) so local and test environments never touch a cluster. The https module is used instead of fetch because Node's fetch cannot take the cluster CA without undici, which is not a dependency. Not chosen: a Job runner inside the api (no isolation, one more process) and a queue (SL-31 scope).


### D-23 · Alert ownership
Alerts carry `usuarioId` from the JWT. Only ADMIN may list and read other users' alerts, for administration; changes are owner-only even for ADMIN. Referenced ids are checked in the api (400 with the field) because the DB only checks the FK, which would surface as a 500.

### D-24 · NFL field mapping from documentation (SL-18)
`AdaptadorAmericano` maps API-Sports american-football games and player statistics to `schemas/americano.schema.json`. No API key was available during development, so the fixtures in `tests/fixtures/nfl_*.json` follow the documented shapes and are **not** a recording. The assumptions to confirm on the first real run:
- Games nest under `game` (`id`, `status.short`, `date.timestamp`, UTC), unlike api-basketball; `scores.<side>.total` and `league.season` are top level.
- Player statistics come per team as `[{team, groups: [{name, players: [{player, statistics: [{name, value}]}]}]}]` with categories Passing, Rushing, Receiving, Defensive (or Defense) and Kicking; made/attempts values (`comp att`, `field goals`, `extra points`) are `"made/attempts"` strings. Exact stat names are the least certain part (aliases are accepted for a few).
- Game status codes (`NS`, `Q1`–`Q4`, `OT`, `HT`, `FT`, `AOT`, `PST`, `CANC`, …).
- The API reports no player position, so `jugador.posicion` stays empty.

Unknown stat names are ignored and unparsable values count as 0, so a wrong name shows up as zeros rather than a failed run. Check a real `/games/statistics/players` response before trusting NFL numbers.


### D-26 · Fallback providers and duplicate games (SL-20)
When API-Sports raises `CuotaAgotadaError` (daily budget) or `ProveedorCaidoError` (5xx, 429 or network error still failing after the retries), `AdaptadorConRespaldo` switches the run to the fallback for every later call. A 4xx (bad key or parameter) does not switch: it fails the run, as before. Since D-38 a plan error does switch. The run records the providers that fed it in `ejecucion_ingesta.proveedor` (`api-sports+balldontlie`) and logs the switch.

Decisions:
- **Liga stays the primary's.** The seeded `liga` rows are keyed on `api-sports`, so the fallback writes into the API-Sports league row. No seed change.
- **Ids are namespaced** `<proveedor>:<id>` for games, teams and players of the fallbacks. Without it a balldontlie game 1000 would silently overwrite an API-Sports game 1000 through `partido(liga_id, proveedor_id)`. Namespacing prevents that overwrite; it does not merge the same real game (below).
- **No cross-provider matching.** Matching by date and team names was rejected: team names and dates (UTC vs local day) are not verified against live data, and a wrong merge would corrupt standings silently. The fallback is kept simple and its limitation is explicit.
- **Box scores follow the game.** Fallback games fetch stats from the fallback. A game fetched from API-Sports before a switch cannot be looked up in the fallback; its row is stored, its box score is skipped with a warning.
- **TheSportsDB free tier has no player box scores.** NFL and Liga MX runs that switch store games and scores only.

Known consequence (inevitable with the current ids): the default CronJob window is yesterday and today. If a day is ingested from the fallback and API-Sports answers the next day, the same game is stored twice (two `partido` rows, two `equipo` rows for the same club, and players split across two `jugador` rows). Standings and form would count the game twice. Mitigation options for later, once live ids are checked: a `partido_alias(proveedor, proveedor_id → partido_id)` table, or a canonical team table with a verified name mapping. Until then, do not rely on fallback data for standings; the `proveedor` column on each run shows when it happened.


### D-27 · balldontlie and TheSportsDB mappings (SL-20)
`adaptadores/balldontlie.py` (NBA, `/games?dates[]`, `/stats?game_ids[]`, cursor pagination) and `adaptadores/thesportsdb.py` (NFL league 4391, Liga MX league 4350, `eventsday.php`) were written from the providers' documentation. The fixtures in `tests/fixtures/balldontlie_*.json` and `thesportsdb_*.json` are synthetic and shaped like those responses. Unverified points to confirm on a first live call:
- balldontlie: `status` strings ("Scheduled", tip-off time, "Final", "Final/OT"), the stat field names (`pts`, `reb`, `fg3m`, …), `min` as "mm:ss", and the `datetime` field in UTC.
- TheSportsDB: `strStatus` values, `strTime` taken as UTC, `intRound` as the jornada.
- balldontlie needs a key (`BALLDONTLIE_API_KEY`); without it the NBA fallback is disabled and NBA behaves as before. TheSportsDB uses its public test key `123` by default (it was `3` until TheSportsDB retired that key; checked live on 2026-11-23).


### D-28 · Model artifacts in PostgreSQL
Each trained model is serialized with joblib and stored in `modelo_artefacto.contenido` (BYTEA, with `sha256` and size). `modelo_prediccion.artefacto_uri` is `db://<modelo_artefacto.id>`. Predicciones replicas load the same bytes from the database, so no shared volume (PVC) is needed to keep them in sync, and a rollback is a change of the active row. Trade-off: artifacts are small (scikit-learn linear and tree models, well under a few MB) and the database is the only shared state; if models grow, move the bytes to object storage and keep the `db://` scheme for the old rows.


### D-29 · Synthetic demo data
`ingesta seed-demo` generates deterministic data (`random.Random(semilla)`) with the same normalized records the adapters return, validates every metrics line against the JSON Schemas and writes through `RepositorioPostgres`. It exists so the predictions work and the frontend can be developed without a live API-Sports quota. It requires `--confirmar`, records an `ejecucion_ingesta` row with proveedor `demo`, and is referenced by no CronJob.


### D-30 · Holdout and what gets stored
Train on the first 80 % of distinct dates, validate on the rest. The cut falls between dates, so a game never appears on both sides. The artifact is the model fitted on the training part, so the stored `metrica_error` describes exactly the bytes in `modelo_artefacto`. Trade-off: the last 20 % of games do not feed the stored model; a later version can refit on all data and keep the holdout metric as a validation record.


### D-31 · Activation rule
A new version is activated only when its metric is strictly better than its baseline (log-loss below the class priors; MAE below the rolling average). If another version is already active for the same (deporte, tipo), the candidate must also be no worse than it (`metrica <= metrica_error` of the active row). Both metrics are on the same name, so the comparison is valid, although each holdout covers a different period. Activation is one transaction that locks the group. A candidate that does not beat its baseline is never activated, even when nothing is active: the endpoint then reports that there is no active model.


### D-32 · First model choices
- Team windows of 10 games; rest days capped at 14. Each season is a separate `liga` row with its own teams, so history does not cross seasons (a season start has no history, imputed).
- NBA and NFL outcomes are `L`/`V`: tied games are dropped from training and from the holdout. Futbol keeps `E`.
- NFL player targets are the `yardas` of the passing, rushing and receiving groups. A row without that group is not a training row for that target.
- Gradient boosting: 200 trees, depth 3, learning rate 0.05, subsample 0.8, fixed seed.
- Artifacts are pickles (joblib). Load only bytes that this service wrote to the database; a compromised database would mean code execution in the predicciones pod.


### D-33 · Synchronous prediction endpoints
Generation, precision and training run inside the request and answer 200 with the result. There is no job queue yet: a training run longer than the api timeout returns 503 to the client while predicciones may still finish. Each request opens one psycopg connection (autocommit, `connect_timeout` 5 s) and closes it at the end; a pool is future work. Re-running generation replaces the rows of the same game (or player and game) and model in one transaction, because `pronostico_partido` and `proyeccion_jugador` have no unique key.


### D-34 · Response casing and dotted metric keys
The Node proxy passes predicciones bodies through, so predicciones answers camelCase like the rest of the public JSON (CONVENTIONS §3). Its request bodies stay snake_case; the api maps them explicitly. Projection `metricas` uses the flat dotted keys of `datos.aplanar_metricas` (`pase.yardas`) rather than nested objects: the same keys the models and the precision comparison use, and no re-nesting code on the way out. The frontend reads NFL projections with `metricas["pase.yardas"]`.


### D-35 · Admin activation bypasses the baseline rule
`POST /modelos/{id}/activar` sets the model active without the D-31 check (metric better than baseline, no worse than the active model). It exists so an admin can roll back or force a version after reviewing the metrics. The check still happens for automatic activation inside `POST /modelos/reentrenar`.

### D-36 · Demo data strong enough to train on
With the first seeder (team strength gap moving an NBA margin by ~3 points against ~14 of noise, NFL yardage independent of the rival, 60 days) no outcome model beat the home-win baseline, so the forecasts screen stayed empty. The models were left alone (D-32): real data, not the demo, should drive model choices. Instead `demo.py` scales the strength gap per sport (`EFECTO_FUERZA_BASQUETBOL` 22 points, `EFECTO_FUERZA_AMERICANO` 0.9 and `EFECTO_FUERZA_FUTBOL` 1.4 on the log scoring rate), NFL yards per catch and per carry and Liga MX shot volume grow with the gap, and `--dias` defaults to 240 (NFL reaches ~140 games, above the 60-game minimum). Checked with seeds 7, 42 and 2026: all six models activate through the D-31 rule. Score distributions stay plausible (NBA 225 total points, 60 % home wins; Liga MX 3.0 goals, 19 % draws; NFL 46 points). `test_la_fuerza_del_equipo_persiste_entre_mitades_de_temporada` guards the signal. Accuracy on demo data says nothing about accuracy on real games.

### D-37 · Seed in the image, run on every api pod start
In the cluster the database is private to the network (AKS when this was decided; RDS on EKS since infra D-38) and the production image has no `tsx`, so `pnpm db:seed` cannot run against it, yet `ingesta run` fails with `LigaNoSembradaError` until the three `liga` rows exist, and `/api/ingestas/ejecutar` and `/api/modelos/reentrenar` need an ADMIN. The seed moved from `prisma/seed.ts` to `src/seed.ts`, so `tsc` builds it into `dist/seed.js`, and the chart runs it as a second initContainer after `prisma migrate deploy`. Every write is an upsert with `update: {}`, so it never changes existing rows (a changed admin password in the secret store does not reset the user). Two pods starting together can race on the same insert; a unique violation (P2002) is retried once. **Alternatives:** a Helm/Argo CD hook Job (one run per sync, but one more ordering rule next to the smoke hook), or a manual Job (a step to forget on every fresh environment).


### D-38 · Plan errors switch to the fallback
On staging (2026-11-23) the free API-Sports plan answered every request with HTTP 200 and `{"errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}}` (and, for older dates, `…access to this date, try from <yesterday> to <tomorrow>.`). The current seasons and a past-season backfill are both out of reach, so no real data could be ingested. The client now raises `PlanSinAccesoError` for an `errors.plan` body, without retrying, and `AdaptadorConRespaldo` treats it like `CuotaAgotadaError` and `ProveedorCaidoError`. Other `errors` bodies (bad key, bad parameter) still fail the run: those are bugs to fix. **Effect:** with `FALLBACK_HABILITADO=true`, NBA comes from balldontlie (needs `BALLDONTLIE_API_KEY`) and NFL and Liga MX from TheSportsDB (games and scores only, no box scores). With fallback off, nothing changes: the run fails, now with the plan message. The D-26 duplicate risk is smaller with the free plan, because API-Sports never answers for the same day. **Rejected:** retrying (the answer does not change), and moving the seasons to 2024 (the date limit still blocks every past day). **Verified live** on staging (2026-11-23, fallback on, TheSportsDB key `123`): NFL and Liga MX runs for 2026-11-22 switched to TheSportsDB and stored 3 games each, with no box scores, as expected from the free tier.

## 3. Known limitations

- Generated forecasts and projections use the games and lines in the database at call time; no scheduled regeneration yet (a scheduled job is future work).
- `GET /api/pronosticos` newest-per-game uses Prisma `distinct` and counts the total by loading the distinct ids; fine for the course data volume, not for millions of rows.
- `/api/partidos?fecha=` filters a UTC day; a 9 pm Mexico game shows up on the next UTC date.
- Box-score field names from api-basketball were mapped from documentation and recorded fixtures; confirm against a live response once a key is available.
- Ingestion writes straight to PostgreSQL, bypassing the api, so catalog cache entries can be stale for up to `CACHE_TTL_S` (60 s) after an ingestion run.
- Rate limits are per client IP and behind one trusted proxy hop; a Redis outage makes the limit per replica instead of global.
- NFL field names are documentation-based (D-24) and `partido.jornada` stays empty because the provider's week labels are not a clean number.
- Liga MX (D-25): the api-football field mapping, the status codes and the `round` → `jornada` parsing come from the v3 documentation. The fixtures in `services/ingesta/tests/fixtures/ligamx_*.json` are synthetic, shaped like that documentation (player and club names are invented). Confirm the field names, that `passes.accuracy` is a count of accurate passes (stored as a percentage of `passes.total`), the string-typed `games.rating`, and the position values against a live response once a key is available.
- Liga MX metrics: a provider null on a required metric (`goles`, `asistencias`) is stored as 0, a null on an optional metric is left out of `metricas`. Squad players with null minutes (never on the pitch) are not stored.
- Fallback duplicates (D-26): the same real game ingested from API-Sports and from a fallback is stored twice, and so are its teams and players. Fallback data should not feed standings until a merge exists.
- Fallback box scores (D-26): NFL and Liga MX fallback runs store no player stats.

## 4. Future work

- OpenAPI generated from the zod schemas (for Schemathesis contract tests, proposal §4.4).
- Testcontainers instead of the CI service container for integration tests.
- Materialized views for season averages if JSONB aggregation gets slow.
