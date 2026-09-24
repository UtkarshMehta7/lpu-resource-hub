"""Migrating at startup: it runs, it is safe to run twice at once, and a
failure stops the app rather than letting it serve a schema it does not match.

This exists because the rule it replaces failed twice in production. Code
reached the deployed instance ahead of its migration, and the feature answered
500 until somebody with the connection string ran alembic by hand.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Environment, Settings
from app.db.migrations import MIGRATION_LOCK_ID, upgrade_to_head

pytestmark = pytest.mark.db


def test_it_brings_the_schema_to_head(db_settings: Settings) -> None:
    engine = create_engine(str(db_settings.database_url))
    try:
        upgrade_to_head(engine, db_settings)
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == "0021"
    finally:
        engine.dispose()


def test_two_instances_booting_at_once_do_not_race(db_settings: Settings) -> None:
    """The reason the old rule existed. An advisory lock settles it: one
    migrates, the other waits and then finds nothing to do."""
    engine = create_engine(str(db_settings.database_url), pool_size=5)
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = [pool.submit(upgrade_to_head, engine, db_settings) for _ in range(3)]
            for result in results:
                result.result()  # raises if any of them failed
    finally:
        engine.dispose()


def test_the_lock_is_released_afterwards(db_settings: Settings) -> None:
    """A held lock would block every later boot forever."""
    engine = create_engine(str(db_settings.database_url))
    try:
        upgrade_to_head(engine, db_settings)
        with engine.connect() as connection:
            held = connection.execute(
                text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = :key"),
                {"key": MIGRATION_LOCK_ID % (2**31)},
            ).scalar_one()
            assert held == 0
    finally:
        engine.dispose()


def test_production_migrates_itself_without_being_told(db_settings: Settings) -> None:
    """It must not depend on an environment variable being set.

    render.yaml only governs a Blueprint-synced service. The live service was
    configured by hand, so RUN_MIGRATIONS_ON_START never reached it and the
    site stayed broken with the fix already deployed.
    """
    production = db_settings.model_copy(update={"app_env": Environment.PRODUCTION})

    assert production.run_migrations_at_boot is True


def test_development_does_not(db_settings: Settings) -> None:
    """A schema changing under you mid-task is its own kind of unpleasant."""
    assert db_settings.run_migrations_at_boot is False


def test_an_explicit_setting_still_wins(db_settings: Settings) -> None:
    production = db_settings.model_copy(
        update={"app_env": Environment.PRODUCTION, "run_migrations_on_start": False}
    )

    assert production.run_migrations_at_boot is False


def test_readiness_reports_a_failed_migration(db_settings: Settings) -> None:
    """Starting degraded is only defensible if the degradation is visible.

    Refusing to start was worse: the deploy failed, the previous image kept
    serving, and the reason was only in logs I could not reach.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(db_settings)
    with TestClient(app) as client:
        app.state.migration_error = "ProgrammingError: relation does not exist"

        response = client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database"] == "ok", "the database is fine; the schema is not"
        assert "relation does not exist" in body["migrations"]
