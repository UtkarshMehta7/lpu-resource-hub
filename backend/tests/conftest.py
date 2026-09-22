"""Shared pytest fixtures.

Settings are built explicitly so results do not depend on a developer's local
configuration. The only value read from outside is TEST_DATABASE_URL (from the
environment, else from backend/.env), used by tests marked ``db``; those tests
are skipped with a clear reason when it is not configured.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Environment, Settings
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.modules.users.models import CoordinatorScopeType, User, UserRole

# Syntactically valid but never contacted: non-db tests do not run the app
# lifespan, so no connection is attempted.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"
TEST_ORIGIN = "http://localhost:5173"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV_FILE = BACKEND_ROOT / ".env"
# Only used to satisfy Settings' min_length validation in tests; never a real secret.
TEST_JWT_SECRET_KEY = "test-only-jwt-signing-key-not-for-production-use-00000"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": Environment.TEST,
        "database_url": UNUSED_DATABASE_URL,
        "cors_origins": TEST_ORIGIN,
        "log_level": "WARNING",
        "jwt_secret_key": TEST_JWT_SECRET_KEY,
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


def _resolve_test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND_ENV_FILE).get(
        "TEST_DATABASE_URL"
    )


@pytest.fixture(scope="session")
def migrated_test_database_url() -> str:
    """Runs `alembic upgrade head` against TEST_DATABASE_URL once per session.

    Exercises the real migration pipeline instead of `Base.metadata.create_all()`,
    which this project's conventions forbid. Skips (like the old db_settings
    fixture did) when TEST_DATABASE_URL isn't configured.
    """
    url = _resolve_test_database_url()
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured (set it in backend/.env or the environment)"
        )
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to migrate the test database:\n{result.stdout}\n{result.stderr}")
    return url


@pytest.fixture
def db_settings(migrated_test_database_url: str) -> Settings:
    return make_settings(database_url=migrated_test_database_url)


TABLES_TO_CLEAN = (
    "application_events, applications, opportunity_skills, opportunities, "
    "project_publications, publication_authors, publications, "
    "project_members, project_skills, project_research_areas, projects, "
    "refresh_tokens, audit_logs, tag_suggestions, tag_aliases, user_skills, "
    "user_research_areas, student_profiles, researcher_profiles, research_areas, "
    "skills, departments, schools, users"
)


@pytest.fixture
def clean_db(migrated_test_database_url: str) -> Iterator[None]:
    """Truncates every domain table before and after each test, for isolation."""
    engine = create_engine(migrated_test_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {TABLES_TO_CLEAN} CASCADE"))
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {TABLES_TO_CLEAN} CASCADE"))
        engine.dispose()


@dataclass(frozen=True, slots=True)
class SeededUser:
    id: uuid.UUID
    email: str
    role: UserRole
    access_token: str


@pytest.fixture
def seed_user(db_settings: Settings) -> Callable[..., SeededUser]:
    """Inserts a user directly via the ORM and returns a ready-to-use access token.

    research_coordinator/admin can't self-register through the API (same
    constraint scripts/create_admin.py works around), so authorization tests
    need a way to seed them directly.
    """
    engine = create_engine(str(db_settings.database_url))
    session_factory = sessionmaker(bind=engine)

    def _seed(
        role: UserRole,
        *,
        is_active: bool = True,
        email: str | None = None,
        department_id: uuid.UUID | str | None = None,
        coordinator_scope_type: CoordinatorScopeType | None = None,
        coordinator_scope_id: uuid.UUID | str | None = None,
    ) -> SeededUser:
        user = User(
            email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("not-used-directly-seeded12"),
            full_name=f"Seeded {role.value}",
            role=role,
            is_active=is_active,
            department_id=uuid.UUID(str(department_id)) if department_id is not None else None,
            coordinator_scope_type=coordinator_scope_type,
            coordinator_scope_id=(
                uuid.UUID(str(coordinator_scope_id)) if coordinator_scope_id is not None else None
            ),
        )
        with session_factory() as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            token = create_access_token(user.id, user.role.value, db_settings)
            return SeededUser(id=user.id, email=user.email, role=user.role, access_token=token)

    return _seed
