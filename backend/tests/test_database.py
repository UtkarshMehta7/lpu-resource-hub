"""Real PostgreSQL connectivity. Requires TEST_DATABASE_URL (skipped otherwise)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import check_database_connection, create_db_engine
from app.main import create_app

pytestmark = pytest.mark.db


def test_select_one_against_postgresql(db_settings: Settings) -> None:
    engine = create_db_engine(db_settings)
    try:
        check_database_connection(engine)
        with engine.connect() as connection:
            server_version = connection.execute(text("SHOW server_version_num")).scalar_one()
        assert int(server_version) >= 160000, "PostgreSQL 16 or newer is required"
    finally:
        engine.dispose()


def test_readiness_with_real_database(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    # `migrations` joined the probe so a schema behind the code is visible
    # from outside rather than found one broken button at a time (ADR 0024).
    assert response.json() == {"status": "ok", "database": "ok", "migrations": "ok"}
