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

from app.core.config import Settings
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


def test_it_is_off_unless_asked_for(db_settings: Settings) -> None:
    """Local work and the test suite migrate explicitly; a surprise schema
    change while you are mid-task is its own kind of unpleasant."""
    assert Settings.model_fields["run_migrations_on_start"].default is False
