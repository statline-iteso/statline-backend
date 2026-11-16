# syntax=docker/dockerfile:1
# statline/predicciones: multi-stage build. Context is the repo root:
#   docker build -f services/predicciones/Dockerfile -t statline/predicciones:local .
#   docker build -f services/predicciones/Dockerfile --target test .   # lint + types + tests

FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

FROM base AS deps
COPY services/predicciones/pyproject.toml services/predicciones/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS test
RUN uv sync --frozen --no-install-project
COPY services/predicciones/ ./
RUN uv sync --frozen \
 && uv run ruff check . \
 && uv run ruff format --check . \
 && uv run mypy \
 && uv run pytest

FROM deps AS build
COPY services/predicciones/ ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home predicciones
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8000
CMD ["uvicorn", "predicciones.main:app", "--host", "0.0.0.0", "--port", "8000"]
