"""Application factory.

Run locally with::

    uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import create_auth_rate_limiter
from app.db.session import check_database_connection, create_db_engine, create_session_factory
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.users.router import router as users_router

API_V1_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_db_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    try:
        check_database_connection(engine)
    except SQLAlchemyError as exc:
        reason = getattr(exc, "orig", exc)
        if settings.is_production:
            logger.critical(
                "Database connection FAILED (%s): %s", settings.database_summary(), reason
            )
            engine.dispose()
            raise
        logger.error(
            "Database connection FAILED (%s): %s -- Is PostgreSQL running? "
            "Check DATABASE_URL in backend/.env. Starting anyway; /health/ready will report 503.",
            settings.database_summary(),
            reason,
        )
    else:
        logger.info("Database connection OK (%s)", settings.database_summary())

    logger.info("%s started (env=%s)", settings.app_name, settings.app_env.value)
    try:
        yield
    finally:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Prototype research platform. Not an official LPU system.",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.auth_rate_limiter = create_auth_rate_limiter()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # The refresh-token cookie requires credentialed CORS.
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)

    # Probes live at the root; business APIs are mounted under /api/v1.
    app.include_router(health_router)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(users_router, prefix=API_V1_PREFIX)
    return app
