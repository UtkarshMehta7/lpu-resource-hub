"""Bring the schema up to date at startup.

The rule used to be that migrations are a release step and never run on
container start, because two instances booting at once would race. That rule
protected against a problem this deployment does not have, and cost more than
it saved: twice, code that needed a migration reached production before the
migration did, and the feature answered 500 until somebody with the connection
string ran alembic by hand.

There is no lock here, and that is deliberate. The usual answer to the race is
a session-level `pg_advisory_lock`, and it is wrong against this database: the
connection string points at Neon's *pooler*, which is PgBouncer in transaction
mode. A session-level lock is taken on a backend connection that is handed
straight back to the pool, so it is never released and every later boot waits
on it forever. The container hung before binding its port and the deploy was
cancelled -- the schema stayed behind, which is the failure this whole thing
exists to prevent.

This service runs one instance with WEB_CONCURRENCY=1, so there is no second
migrator to race with. If that ever changes, the lock must be taken on a
*direct* (non-pooled) Neon endpoint, or be a transaction-level lock around a
single-transaction migration. Not this.

Off by default; production turns it on (see Settings.run_migrations_at_boot).
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import Settings

logger = logging.getLogger(__name__)


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # env.py reads the URL from settings, not from the ini, so the deployed
    # instance migrates the database it is actually connected to.
    config.set_main_option("sqlalchemy.url", str(settings.database_url))
    return config


def upgrade_to_head(settings: Settings) -> None:
    """Apply outstanding migrations. Must return, or the app never serves."""
    logger.info("Applying database migrations…")
    command.upgrade(_alembic_config(settings), "head")
    logger.info("Database schema is up to date.")
