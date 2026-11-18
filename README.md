# StatLine — Backend

**StatLine** is a web platform for unified sports statistics and forecasts across **NBA**, **NFL** and **Liga MX**. Scheduled jobs pull games and box scores from API-Sports and store them in PostgreSQL (sport-specific metrics in JSONB, validated against a JSON Schema per sport). A REST API serves standings, calendars, box scores and player comparisons; a Python service produces match-outcome probabilities and player projections from versioned models.

This repository hosts the three backend services and the shared JSON Schemas:

| Service | Stack | Image | Status |
|---|---|---|---|
| [`services/api`](services/api) | Node 20, Express, TypeScript, Prisma, JWT + bcrypt | `statline/api` | Auth, usuarios, ligas, equipos, jugadores, partidos ✅ · remaining routes pending |
| [`services/ingesta`](services/ingesta) | Python 3.12, httpx, pandas, psycopg, jsonschema | `statline/ingesta` | NBA end to end ✅ · NFL adapter ✅ (from docs, unverified live) · Liga MX ✅ (field mapping unverified, D-16) · fallbacks pending |
| [`services/predicciones`](services/predicciones) | Python 3.12, FastAPI, scikit-learn | `statline/predicciones` | Probes and contract ✅ · models pending |
| [`schemas/`](schemas) | JSON Schema 2020-12 | — | NBA, NFL, Liga MX ✅ |

## Related Repositories

- [statline-frontend](https://github.com/statline-iteso/statline-frontend): React SPA that consumes this API.
- [statline-infra](https://github.com/statline-iteso/statline-infra): Terraform (Azure, AKS), GitOps, and the project-wide docs (data model, API design, backlog, pending work).

## Documentation

- [AGENTS.md](AGENTS.md): Project overview, scope, stack, and rules for contributors and AI agents.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Services, data model, HTTP routes, ingestion flow, and the deployment contract for infra.
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md): Coding guidelines, errors, testing, and Git rules.
- [docs/DECISIONS.md](docs/DECISIONS.md): Decisions, rationale, trade-offs, and future work.
- [docs/BACKLOG.md](docs/BACKLOG.md): This repo's issues.

## Quickstart

```bash
# 1. Dependencies
pnpm install                                   # api (pnpm workspace)
(cd services/ingesta && uv sync)               # Python services use uv
(cd services/predicciones && uv sync)

# 2. Local PostgreSQL 16 + Redis 7
cp .env.example .env
docker compose up -d --wait

# 3. Schema and seed (the three leagues; admin if SEED_ADMIN_PASSWORD is set)
pnpm --filter @statline/api prisma:generate
pnpm --filter @statline/api prisma:migrate
pnpm --filter @statline/api db:seed

# 4. Run
pnpm --filter @statline/api dev                                       # API on :3000
(cd services/predicciones && uv run uvicorn predicciones.main:app --reload --port 8000)
(cd services/ingesta && uv run ingesta run basquetbol --desde 2026-11-14)   # needs API_SPORTS_KEY

# 5. Optional, dev only: synthetic demo data (no API key, never run by CronJobs)
(cd services/ingesta && uv run ingesta seed-demo --confirmar)   # --deportes, --semilla, --dias
```

## Testing and quality

```bash
pnpm --filter @statline/api lint typecheck      # ESLint, tsc
pnpm --filter @statline/api test:coverage       # Jest + Supertest, fails under 70 %
cd services/ingesta && uv run ruff check . && uv run mypy && uv run pytest     # same for predicciones
DATABASE_URL=postgresql://statline:statline@localhost:5432/statline \
  uv run pytest -m integration --no-cov        # ingesta SQL against the migrated schema
```

On Windows with Smart App Control, native wheels (numpy) inside `.venv` can be blocked; run the Python checks in Docker instead: `docker build -f services/ingesta/Dockerfile --target test .`

## Docker images

Every image builds from the repo root (the ingesta image needs `schemas/`):

```bash
docker build -f services/api/Dockerfile          -t statline/api:local .
docker build -f services/ingesta/Dockerfile      -t statline/ingesta:local .
docker build -f services/predicciones/Dockerfile -t statline/predicciones:local .
```

Pushing to Docker Hub is done by `cd.yml` after a merge (pending, SL-53). What the Kubernetes manifests need (ports, probes, env vars, args) is in [docs/ARCHITECTURE.md §8](docs/ARCHITECTURE.md#8-deployment-contract-for-the-infra-chart).
