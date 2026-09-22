"""Shared pytest fixtures.

Settings are built explicitly so results do not depend on a developer's local
configuration. The only value read from outside is TEST_DATABASE_URL (from the
environment, else from backend/.env), used by tests marked ``db``; those tests
are skipped with a clear reason when it is not configured.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Environment, Settings
from app.main import create_app

# Syntactically valid but never contacted: non-db tests do not run the app
# lifespan, so no connection is attempted.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
TEST_ORIGIN = "http://localhost:5173"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV_FILE = BACKEND_ROOT / ".env"
# Only used to satisfy Settings' min_length validation in tests; never a real secret.
TEST_JWT_SECRET_KEY = "test-only-jwt-signing-key-not-for-production-use-00000"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": Environment.TEST,
        "database_url": UNUSED_DATABASE_URL,
        "cors_origins": TEST_ORIGIN,
        "log_level": "WARNING",
        "jwt_secret_key": TEST_JWT_SECRET_KEY,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Client WITHOUT the lifespan: no database connection is attempted."""
    yield TestClient(app)


def _resolve_test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND_ENV_FILE).get(
        "TEST_DATABASE_URL"
    )


@pytest.fixture(scope="session")
def migrated_test_database_url() -> str:
    """Runs `alembic upgrade head` against TEST_DATABASE_URL once per session.

    Exercises the real migration pipeline instead of `Base.metadata.create_all()`,
    which this project's conventions forbid. Skips (like the old db_settings
    fixture did) when TEST_DATABASE_URL isn't configured.
    """
    url = _resolve_test_database_url()
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured (set it in backend/.env or the environment)"
        )
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to migrate the test database:\n{result.stdout}\n{result.stderr}")
    return url


@pytest.fixture
def db_settings(migrated_test_database_url: str) -> Settings:
    return make_settings(database_url=migrated_test_database_url)


@pytest.fixture
def clean_db(migrated_test_database_url: str) -> Iterator[None]:
    """Truncates the auth tables before and after each test, for isolation."""
    engine = create_engine(migrated_test_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE refresh_tokens, users CASCADE"))
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE refresh_tokens, users CASCADE"))
        engine.dispose()
