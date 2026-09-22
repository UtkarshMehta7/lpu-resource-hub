"""Engine, session factory and request-scoped session dependency.

The engine is created by the application lifespan and stored on
``app.state`` so that each app instance (including test instances) owns its
own connection pool instead of relying on an import-time global.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"connect_timeout": settings.db_connect_timeout},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def check_database_connection(engine: Engine) -> None:
    """Run ``SELECT 1``. Raises ``sqlalchemy.exc.OperationalError`` if unreachable."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed afterwards."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
