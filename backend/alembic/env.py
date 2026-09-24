"""Alembic migration environment.

The database URL comes from application settings (DATABASE_URL), never from
alembic.ini. Future ORM models become visible to autogenerate by being
imported in one place before ``target_metadata`` is read (added in Step 1).
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.db import model_registry  # noqa: F401
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
database_url = str(get_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # One transaction per migration, not one for the whole upgrade.
            #
            # PostgreSQL will not let a newly added enum value be *used* in
            # the transaction that added it, unless the type itself was
            # created there too. Migration 0020 adds 'ended' to
            # collaboration_status and 0021 selects on it: fine on a database
            # built from scratch, where the type is created in the same run,
            # and fatal on a database that already had the type -- which is
            # every deployed one. It broke production and passed locally,
            # which is precisely the shape of bug this setting prevents.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
