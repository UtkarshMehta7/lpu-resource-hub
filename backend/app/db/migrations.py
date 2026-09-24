"""Bring the schema up to date at startup, safely.

The rule used to be that migrations are a release step and never run on
container start, because two instances booting at once would race. That rule
protected a problem the platform does not have -- and it cost more than it
saved. Twice now, code that needed a migration reached production before the
migration did, and the feature answered 500 until somebody with the connection
string ran alembic by hand. The second time, sending a collaboration request
broke for real users.

The race is a real concern, and a PostgreSQL advisory lock settles it: whoever
boots first holds the lock and migrates; everyone else waits and then finds
nothing to do. That is how this is done in production systems that deploy
from a container, and it is strictly safer than a human remembering.

Off by default. Local development and the test suite migrate explicitly, and
should keep doing so -- surprise schema changes while you are working are
their own kind of unpleasant. Deployments turn it on (`render.yaml`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, text

from alembic import command
from app.core.config import Settings

logger = logging.getLogger(__name__)

#: Any constant will do; it only has to be the same in every instance. Chosen
#: once and never changed, or two versions of the app would not see each
#: other's lock.
MIGRATION_LOCK_ID = 8_274_119_055


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # env.py reads the URL from settings, not from the ini, so the deployed
    # instance migrates the database it is actually connected to.
    config.set_main_option("sqlalchemy.url", str(settings.database_url))
    return config


def upgrade_to_head(engine: Engine, settings: Settings) -> None:
    """Run any outstanding migrations, once, across every booting instance.

    Holds a session-level advisory lock for the duration. A second instance
    booting at the same moment blocks here rather than running the same
    migration concurrently, and proceeds as soon as the first is finished.
    """
    with engine.connect() as connection:
        logger.info("Waiting for the migration lock…")
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_ID})
        connection.commit()
        try:
            logger.info("Applying database migrations…")
            command.upgrade(_alembic_config(settings), "head")
            logger.info("Database schema is up to date.")
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_ID})
            connection.commit()
