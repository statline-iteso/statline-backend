# Backend Conventions

Short rules so they get followed. If one gets in the way, change it here in a PR and say why.

## 1. TypeScript (api)

- `strict`, `noUncheckedIndexedAccess`. No `any` except the one documented in `lib/crud.ts`; use `unknown` + zod.
- Named exports only. Files kebab-case (`error-handler.ts`).
- Validate every input with zod (`schemas.ts`); infer types from schemas.
- Routes only parse → call Prisma or a pure function → respond. Logic that can be pure (standings, form) lives in `src/lib/` with its own unit tests.
- Express 4 doesn't forward rejected promises: wrap async handlers with `ah()`.
- Status codes: 200 read, 201 create, 204 delete, 400 invalid, 401 unauthenticated, 403 forbidden, 404 missing, 409 duplicate, 500 bug, 503 dependency down.
- Logs with pino (`req.log`), never `console.log` (ESLint enforces it). Never log tokens, passwords or `DATABASE_URL`.

## 2. Python (ingesta, predicciones)

- Python 3.12, `uv` with a committed `uv.lock`. `ruff` (E, F, I, B, UP, SIM, RUF; line 100) and `mypy --strict`.
- Package layout `src/<pkg>/`; settings with pydantic-settings; dataclasses (`frozen=True`) for normalized records.
- I/O at the edges (`obtener_*`, `repositorio`), pure functions in the middle (`normalizar*`, validation) so tests need no network.
- SQL in `repositorio.py` only, parameterized (`%s`), never string formatting.
- Logging with `logging`; no `print`.

## 3. Naming

| Thing | Style | Example |
|---|---|---|
| Domain names | Spanish, as in the proposal | `Partido`, `obtener_partidos`, `/api/jugadores` |
| JSON over HTTP | camelCase | `marcadorLocal` |
| DB tables/columns | snake_case | `marcador_local` |
| Env vars | UPPER_SNAKE_CASE | `API_SPORTS_KEY` |
| Error codes | UPPER_SNAKE_CASE | `VALIDATION_ERROR` |

## 4. Database

- Schema changes only through `prisma migrate dev --name <change>`; commit the migration folder.
- Migrations must be backward compatible with the previous image (expand → deploy → contract).
- New upsert targets need a unique constraint in Prisma first.

## 5. Tests

- api: Jest + Supertest against `createApp` with `jest-mock-extended` Prisma mocks; pure logic tested directly.
- Python: pytest; HTTP with `respx`; adapters with recorded fixtures in `tests/fixtures/`; SQL with `-m integration` against a migrated PostgreSQL.
- Coverage ≥ 70 % lines per service (CI fails below). Test names describe behavior.

## 6. Docker

- Multi-stage; build from the repo root; final stage non-root and without build tools; `linux/amd64`.
- Python images have a `test` stage that runs lint, types and tests.

## 7. Git and PRs

- Branches from `develop`: `feature/<issue>-<desc>`, `fix/<issue>-<desc>`. Conventional Commits (`feat(api): …`, `fix(ingesta): …`).
- PRs: template filled, `Closes #N`, CI green, one approval. Squash merge for feature/fix; merge commit for release/hotfix.
- **No AI attribution** in commits, PRs or issues.
