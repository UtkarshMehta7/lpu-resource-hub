"""Shared pytest fixtures.

Settings are built explicitly so results do not depend on a developer's local
configuration. The only value read from outside is TEST_DATABASE_URL (from the
environment, else from backend/.env), used by tests marked ``db``; those tests
are skipped with a clear reason when it is not configured.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app

# Syntactically valid but never contacted: non-db tests do not run the app
# lifespan, so no connection is attempted.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
TEST_ORIGIN = "http://localhost:5173"
BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": Environment.TEST,
        "database_url": UNUSED_DATABASE_URL,
        "cors_origins": TEST_ORIGIN,
        "log_level": "WARNING",
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


@pytest.fixture
def db_settings() -> Settings:
    url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND_ENV_FILE).get(
        "TEST_DATABASE_URL"
    )
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured (set it in backend/.env or the environment)"
        )
    return make_settings(database_url=url)
