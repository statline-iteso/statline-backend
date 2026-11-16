# syntax=docker/dockerfile:1
# statline/ingesta: multi-stage build. Context is the repo root (it needs schemas/):
#   docker build -f services/ingesta/Dockerfile -t statline/ingesta:local .
#   docker build -f services/ingesta/Dockerfile --target test .   # lint + types + tests

FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

FROM base AS deps
COPY services/ingesta/pyproject.toml services/ingesta/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS test
RUN uv sync --frozen --no-install-project
COPY schemas /schemas
ENV TEST_SCHEMAS_DIR=/schemas
COPY services/ingesta/ ./
RUN uv sync --frozen \
 && uv run ruff check . \
 && uv run ruff format --check . \
 && uv run mypy \
 && uv run pytest

FROM deps AS build
COPY services/ingesta/ ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home ingesta
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
COPY schemas /app/schemas
ENV PATH="/app/.venv/bin:$PATH" SCHEMAS_DIR=/app/schemas PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8080
# Each CronJob overrides the args: ["run", "basquetbol"], ["run", "americano"], ["run", "futbol"].
ENTRYPOINT ["ingesta"]
CMD ["serve"]
