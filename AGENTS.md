# StatLine — Backend · Agent Context

> Read this first. Deeper docs:
> - `docs/ARCHITECTURE.md`: services, data model, routes, ingestion flow, deployment contract
> - `docs/CONVENTIONS.md`: how code is written, tested and reviewed here
> - `docs/DECISIONS.md`: what we decided, why, limitations and future work
>
> If you change a contract (route, response shape, env var, port, probe, DB schema, JSON Schema), update `docs/ARCHITECTURE.md` in the same change and tell the owner of the affected repo.

## 1. The project in one paragraph

**StatLine** unifies statistics and forecasts for **NBA**, **NFL** and **Liga MX**. Three CronJobs (`ingesta-basquetbol` daily, `ingesta-americano` weekly, `ingesta-futbol` twice a week) pull games and box scores from API-Sports, normalize them through one `AdaptadorDeporte` per sport, validate each line against `schemas/<deporte>.schema.json` and upsert into PostgreSQL. The **api** serves the catalog, standings, box scores, comparisons, watchlists and alerts. **predicciones** runs versioned scikit-learn models (logistic regression for outcomes, gradient boosting for player metrics) registered in `ModeloPrediccion`. Not a fantasy or betting product.

ITESO final project, Fall 2026: **Juan Pablo González** (backend, frontend) and **Ian Rodríguez** (infra, predictions, deployment).

## 2. Scope of this repo

| In | Out |
|---|---|
| `services/api`, `services/ingesta`, `services/predicciones`, `schemas/`, their Dockerfiles and CI | Kubernetes manifests, Terraform, Argo CD (statline-infra) · the SPA (statline-frontend) |

## 3. Stack

| Concern | Choice |
|---|---|
| API | Node 20, Express 4, TypeScript strict (CommonJS), zod, Prisma 5, JWT (jsonwebtoken) + bcryptjs, pino, prom-client, helmet |
| Python services | Python 3.12, uv, pydantic-settings, httpx, pandas, psycopg 3, jsonschema, FastAPI, scikit-learn |
| Data | PostgreSQL 16; schema owned by **Prisma Migrate**; Redis 7 (cache and rate limit, SL-31) |
| Tests | Jest + Supertest (api), pytest + respx (Python); coverage ≥ 70 % enforced; integration tests against PostgreSQL |
| Quality | ESLint, Prettier, tsc · ruff, mypy strict |
| Images | Multi-stage Dockerfiles, non-root, `linux/amd64` |

## 4. Commands

```bash
docker compose up -d --wait                      # PostgreSQL + Redis
pnpm --filter @statline/api dev | test:coverage | lint | typecheck
pnpm --filter @statline/api prisma:migrate | db:seed
cd services/<svc> && uv run pytest | ruff check . | mypy
```

## 5. Layout

```
statline-backend/
├── schemas/                  basquetbol · americano · futbol (.schema.json)
├── services/
│   ├── api/                  prisma/ (schema, migrations, seed) · src/ (app, server, lib, middleware, routes) · test/
│   ├── ingesta/              src/ingesta/ (adaptadores/, ejecutor, repositorio, validacion, cli, servidor) · tests/
│   └── predicciones/         src/predicciones/ (main, schemas, config) · tests/
├── docker-compose.yml · .env.example · .devcontainer/
└── .github/workflows/ci.yml
```

## 6. Rules for agents

1. Stay in scope (§2). New external services or providers need a decision entry.
2. **Prisma owns the schema.** Change `schema.prisma`, generate a migration, and update the SQL in `services/ingesta/src/ingesta/repositorio.py` if a table it writes changed. The integration test must still pass.
3. **Every metrics line is validated** against its JSON Schema before insert. Changing a schema is a contract change (frontend renders these keys).
4. Tests are part of every change; coverage must stay ≥ 70 % per service.
5. No secrets in the repo; `.env` is gitignored, `.env.example` documents every variable.
6. Branches `feature/<issue>-<desc>` / `fix/<issue>-<desc>` from `develop`; squash merge; PR says `Closes #N`; Conventional Commits.
7. **No AI attribution.** Never add yourself as a co-author: no `Co-Authored-By` trailers in commits and no "Generated with …" lines in PR descriptions or issues.
