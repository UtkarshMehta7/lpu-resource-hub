"""Application factory.

Run locally with::

    uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import (
    create_auth_rate_limiter,
    create_collaboration_rate_limiter,
    create_message_rate_limiter,
    create_search_rate_limiter,
)
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.migrations import upgrade_to_head
from app.db.session import check_database_connection, create_db_engine, create_session_factory
from app.jobs.scheduler import start_scheduler
from app.ml import embeddings
from app.modules.admin.accounts_router import admin_router as admin_accounts_router
from app.modules.admin.accounts_router import router as accounts_router
from app.modules.admin.router import org_router as admin_org_router
from app.modules.admin.router import public_org_router
from app.modules.admin.router import router as admin_router
from app.modules.analytics.router import router as analytics_router
from app.modules.applications.router import router as applications_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.bookings.router import router as bookings_router
from app.modules.collaborations.router import router as collaborations_router
from app.modules.facilities.router import router as facilities_router
from app.modules.funding.router import router as funding_router
from app.modules.health.router import router as health_router
from app.modules.messages.router import router as messages_router
from app.modules.notifications.handlers import register_notification_handlers
from app.modules.notifications.router import router as notifications_router
from app.modules.opportunities.router import router as opportunities_router
from app.modules.profiles.router import router as profiles_router
from app.modules.projects.router import router as projects_router
from app.modules.publications.router import router as publications_router
from app.modules.recommendations.router import router as recommendations_router
from app.modules.reports.router import router as reports_router
from app.modules.researchers.router import router as researchers_router
from app.modules.search.router import router as search_router
from app.modules.taxonomy.router import router as taxonomy_router
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

    if settings.run_migrations_on_start:
        try:
            upgrade_to_head(engine, settings)
        except Exception:
            # Serving with a schema the code does not match is worse than not
            # serving: every request against the missing table answers 500,
            # which is exactly the failure this setting exists to prevent.
            logger.critical("Database migration FAILED; refusing to start.")
            engine.dispose()
            raise

    # Handlers turn domain events into notifications (Step 12). Registered
    # here, once per app, rather than at import time.
    register_notification_handlers()

    # Load the embedding model off the request path: without this the first
    # semantic search pays several seconds of model load (measured ~9s cold,
    # ~35ms warm). Skipped entirely when the optional ML extra is absent.
    if embeddings.is_available():
        Thread(target=embeddings.load_model, name="embedding-warmup", daemon=True).start()

    scheduler = None
    if settings.enable_scheduler:
        scheduler = start_scheduler(
            app.state.session_factory, interval_minutes=settings.reminder_interval_minutes
        )

    logger.info("%s started (env=%s)", settings.app_name, settings.app_env.value)
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
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
    app.state.search_rate_limiter = create_search_rate_limiter()
    app.state.collaboration_rate_limiter = create_collaboration_rate_limiter()
    app.state.message_rate_limiter = create_message_rate_limiter()

    # Outermost: every response, including errors, carries the headers.
    app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # The refresh-token cookie requires credentialed CORS.
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # X-Requested-With is the CSRF guard every browser request carries,
        # so it must survive the preflight or nothing works from a browser.
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )
    register_exception_handlers(app)

    # Probes live at the root; business APIs are mounted under /api/v1.
    app.include_router(health_router)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(users_router, prefix=API_V1_PREFIX)
    app.include_router(accounts_router, prefix=API_V1_PREFIX)
    app.include_router(admin_accounts_router, prefix=API_V1_PREFIX)
    app.include_router(admin_router, prefix=f"{API_V1_PREFIX}/admin")
    app.include_router(admin_org_router, prefix=f"{API_V1_PREFIX}/admin")
    app.include_router(public_org_router, prefix=API_V1_PREFIX)
    app.include_router(audit_router, prefix=f"{API_V1_PREFIX}/admin")
    app.include_router(taxonomy_router, prefix=API_V1_PREFIX)
    app.include_router(profiles_router, prefix=API_V1_PREFIX)
    app.include_router(researchers_router, prefix=API_V1_PREFIX)
    app.include_router(projects_router, prefix=API_V1_PREFIX)
    app.include_router(publications_router, prefix=API_V1_PREFIX)
    app.include_router(opportunities_router, prefix=API_V1_PREFIX)
    app.include_router(applications_router, prefix=API_V1_PREFIX)
    app.include_router(collaborations_router, prefix=API_V1_PREFIX)
    app.include_router(messages_router, prefix=API_V1_PREFIX)
    app.include_router(recommendations_router, prefix=API_V1_PREFIX)
    app.include_router(reports_router, prefix=API_V1_PREFIX)
    app.include_router(analytics_router, prefix=API_V1_PREFIX)
    app.include_router(facilities_router, prefix=API_V1_PREFIX)
    app.include_router(bookings_router, prefix=API_V1_PREFIX)
    app.include_router(funding_router, prefix=API_V1_PREFIX)
    app.include_router(notifications_router, prefix=API_V1_PREFIX)
    app.include_router(search_router, prefix=API_V1_PREFIX)
    return app
