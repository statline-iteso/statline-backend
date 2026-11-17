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
| D-15 | 2026-11-16 | NFL adapter (api-american-football, league 1) built from API-Sports documentation, not from a live response | Decided (unverified) |
| D-16 | 2026-11-16 | Liga MX (api-football, league 262) mapped from the provider documentation; unverified against a live response | Decided (limitation) |
| D-17 | 2026-11-16 | Fallback providers (balldontlie for NBA, TheSportsDB for NFL and Liga MX) take over for the rest of a run when API-Sports is out of quota or down; duplicates across providers are not merged | Decided (limitation) |
| D-18 | 2026-11-16 | balldontlie and TheSportsDB mappings built from their documentation, not from live responses | Decided (unverified) |

## 2. Details

### D-02 · Prisma owns the schema
One migration history, applied by the api initContainer. The ingesta repository's SQL is checked against the real migrated schema by the integration test in CI, so drift fails the build.

### D-05 · JSONB instead of tables per sport
Cross-sport queries (a player's lines, a game's box score) stay one table; sport-specific aggregation uses `(metricas->>'puntos')::int`. The engine doesn't validate JSONB shape, hence D-07 and strict schemas.

### D-15 · NFL field mapping from documentation (SL-18)
`AdaptadorAmericano` maps API-Sports american-football games and player statistics to `schemas/americano.schema.json`. No API key was available during development, so the fixtures in `tests/fixtures/nfl_*.json` follow the documented shapes and are **not** a recording. The assumptions to confirm on the first real run:
- Games nest under `game` (`id`, `status.short`, `date.timestamp`, UTC), unlike api-basketball; `scores.<side>.total` and `league.season` are top level.
- Player statistics come per team as `[{team, groups: [{name, players: [{player, statistics: [{name, value}]}]}]}]` with categories Passing, Rushing, Receiving, Defensive (or Defense) and Kicking; made/attempts values (`comp att`, `field goals`, `extra points`) are `"made/attempts"` strings. Exact stat names are the least certain part (aliases are accepted for a few).
- Game status codes (`NS`, `Q1`–`Q4`, `OT`, `HT`, `FT`, `AOT`, `PST`, `CANC`, …).
- The API reports no player position, so `jugador.posicion` stays empty.

Unknown stat names are ignored and unparsable values count as 0, so a wrong name shows up as zeros rather than a failed run. Check a real `/games/statistics/players` response before trusting NFL numbers.

### D-17 · Fallback providers and duplicate games (SL-20)
When API-Sports raises `CuotaAgotadaError` (daily budget) or `ProveedorCaidoError` (5xx, 429 or network error still failing after the retries), `AdaptadorConRespaldo` switches the run to the fallback for every later call. A 4xx (bad key or parameter) does not switch: it fails the run, as before. The run records the providers that fed it in `ejecucion_ingesta.proveedor` (`api-sports+balldontlie`) and logs the switch.

Decisions:
- **Liga stays the primary's.** The seeded `liga` rows are keyed on `api-sports`, so the fallback writes into the API-Sports league row. No seed change.
- **Ids are namespaced** `<proveedor>:<id>` for games, teams and players of the fallbacks. Without it a balldontlie game 1000 would silently overwrite an API-Sports game 1000 through `partido(liga_id, proveedor_id)`. Namespacing prevents that overwrite; it does not merge the same real game (below).
- **No cross-provider matching.** Matching by date and team names was rejected: team names and dates (UTC vs local day) are not verified against live data, and a wrong merge would corrupt standings silently. The fallback is kept simple and its limitation is explicit.
- **Box scores follow the game.** Fallback games fetch stats from the fallback. A game fetched from API-Sports before a switch cannot be looked up in the fallback; its row is stored, its box score is skipped with a warning.
- **TheSportsDB free tier has no player box scores.** NFL and Liga MX runs that switch store games and scores only.

Known consequence (inevitable with the current ids): the default CronJob window is yesterday and today. If a day is ingested from the fallback and API-Sports answers the next day, the same game is stored twice (two `partido` rows, two `equipo` rows for the same club, and players split across two `jugador` rows). Standings and form would count the game twice. Mitigation options for later, once live ids are checked: a `partido_alias(proveedor, proveedor_id → partido_id)` table, or a canonical team table with a verified name mapping. Until then, do not rely on fallback data for standings; the `proveedor` column on each run shows when it happened.

### D-18 · balldontlie and TheSportsDB mappings (SL-20)
`adaptadores/balldontlie.py` (NBA, `/games?dates[]`, `/stats?game_ids[]`, cursor pagination) and `adaptadores/thesportsdb.py` (NFL league 4391, Liga MX league 4350, `eventsday.php`) were written from the providers' documentation. The fixtures in `tests/fixtures/balldontlie_*.json` and `thesportsdb_*.json` are synthetic and shaped like those responses. Unverified points to confirm on a first live call:
- balldontlie: `status` strings ("Scheduled", tip-off time, "Final", "Final/OT"), the stat field names (`pts`, `reb`, `fg3m`, …), `min` as "mm:ss", and the `datetime` field in UTC.
- TheSportsDB: `strStatus` values, `strTime` taken as UTC, `intRound` as the jornada.
- balldontlie needs a key (`BALLDONTLIE_API_KEY`); without it the NBA fallback is disabled and NBA behaves as before. TheSportsDB uses its public test key `3` by default.

### D-09 · Express 4 and CommonJS
The proposal says Express. Express 4 + `ts-jest` in CommonJS avoids ESM test configuration; async errors are forwarded with a small `ah()` wrapper.

## 3. Known limitations

- `/api/partidos?fecha=` filters a UTC day; a 9 pm Mexico game shows up on the next UTC date.
- Box-score field names from api-basketball were mapped from documentation and recorded fixtures; confirm against a live response once a key is available.
- NFL field names are documentation-based (D-15) and `partido.jornada` stays empty because the provider's week labels are not a clean number.
- Liga MX (D-16): the api-football field mapping, the status codes and the `round` → `jornada` parsing come from the v3 documentation. The fixtures in `services/ingesta/tests/fixtures/ligamx_*.json` are synthetic, shaped like that documentation (player and club names are invented). Confirm the field names, that `passes.accuracy` is a count of accurate passes (stored as a percentage of `passes.total`), the string-typed `games.rating`, and the position values against a live response once a key is available.
- Liga MX metrics: a provider null on a required metric (`goles`, `asistencias`) is stored as 0, a null on an optional metric is left out of `metricas`. Squad players with null minutes (never on the pitch) are not stored.
- No rate limiting until SL-31.
- Fallback duplicates (D-17): the same real game ingested from API-Sports and from a fallback is stored twice, and so are its teams and players. Fallback data should not feed standings until a merge exists.
- Fallback box scores (D-17): NFL and Liga MX fallback runs store no player stats.

## 4. Future work

- OpenAPI generated from the zod schemas (for Schemathesis contract tests, proposal §4.4).
- Testcontainers instead of the CI service container for integration tests.
- Materialized views for season averages if JSONB aggregation gets slow.
