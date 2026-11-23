# syntax=docker/dockerfile:1

# ---- builder ----------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG INSTALL_AI=false

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_HTTP_TIMEOUT=600

WORKDIR /app

COPY cli/pyproject.toml cli/uv.lock cli/README.md ./
COPY cli/src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_AI" = "true" ]; then \
      uv sync --locked --no-dev --extra ai; \
    else \
      uv sync --locked --no-dev; \
    fi

# ---- bootstrap (used by `docker compose run --rm init` before config exists) -
FROM python:3.12-slim-bookworm AS bootstrap

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    HF_HOME=/data/cache/hf \
    TORCH_HOME=/data/cache/torch

RUN mkdir -p /data/media /data/skipped /data/cache/hf /data/cache/torch \
    && chown -R appuser:appuser /data /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --chown=appuser:appuser infra ./infra
COPY --chown=appuser:appuser contracts ./contracts

USER appuser

ENTRYPOINT ["photosphere"]
CMD ["--help"]

# ---- runtime (fails docker build if photosphere.config.json is missing) ------
FROM bootstrap AS runtime

COPY --chown=appuser:appuser photosphere.config.json ./photosphere.config.json
