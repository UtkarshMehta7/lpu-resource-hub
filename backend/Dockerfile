# Backend image. Optional: `make dev` / uvicorn locally works without Docker.
FROM python:3.12-slim AS base

# Fail fast, no .pyc, unbuffered logs (so container logs appear immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg needs libpq; build-essential is only needed while installing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so a code change doesn't reinstall the world.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e "."

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Hosts inject the port to bind ($PORT on Render); 8000 is only the local
# default. Binding a hardcoded port means the platform's health check hits
# nothing and the deploy is marked failed.
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Migrations are deliberately NOT run here: a container that migrates on
# start races with itself when scaled. Run `alembic upgrade head` as a
# release step (see docs/deployment.md).
# Shell form on purpose: $PORT has to be expanded at runtime, and exec keeps
# uvicorn as PID 1 so signals still reach it.
CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT}"
