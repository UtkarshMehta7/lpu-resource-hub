"""Migration 0018: coordinators appointed before the scope fix get their scope.

The service layer now keeps scope and department in step, but only from the
next edit onwards. The coordinators already appointed on the deployed
database were left overseeing nothing -- an empty verification queue and 403
on every decision -- so the repair has to run against existing rows, and it
has to leave a deliberately different scope alone.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

from app.core.config import Settings
from app.modules.users.models import CoordinatorScopeType, UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db


def _backfill_sql() -> str:
    """The statement the migration runs, read from the migration itself.

    A retyped copy would silently stop testing the real thing the first time
    one of the two was edited. The file name starts with a digit, so it can
    only be loaded by path, not imported.
    """
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0018_give_existing_coordinators_their_scope.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0018", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sql: str = module.BACKFILL_SQL
    return sql


BACKFILL_SQL = _backfill_sql()


def _scope(settings: Settings, user_id: uuid.UUID) -> tuple[str | None, uuid.UUID | None]:
    engine = create_engine(str(settings.database_url))
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT coordinator_scope_type::text, coordinator_scope_id "
                "FROM users WHERE id = :id"
            ),
            {"id": user_id},
        ).one()
    return row[0], row[1]


def _run_backfill(settings: Settings) -> None:
    engine = create_engine(str(settings.database_url))
    with engine.begin() as connection:
        connection.execute(sa.text(BACKFILL_SQL))


@pytest.fixture
def department_id(db_settings: Settings, clean_db: None) -> uuid.UUID:
    engine = create_engine(str(db_settings.database_url))
    with engine.begin() as connection:
        school = connection.execute(
            sa.text("INSERT INTO schools (id, name) VALUES (:id, :name) RETURNING id"),
            {"id": uuid.uuid4(), "name": "School of Agriculture"},
        ).scalar_one()
        return connection.execute(
            sa.text(
                "INSERT INTO departments (id, school_id, name) "
                "VALUES (:id, :school, :name) RETURNING id"
            ),
            {"id": uuid.uuid4(), "school": school, "name": "Agronomy"},
        ).scalar_one()


def test_a_stranded_coordinator_is_put_over_their_own_department(
    db_settings: Settings, department_id: uuid.UUID, seed_user: Callable[..., SeededUser]
) -> None:
    stranded = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department_id)
    assert _scope(db_settings, stranded.id) == (None, None), "the bug, reproduced"

    _run_backfill(db_settings)

    assert _scope(db_settings, stranded.id) == (
        CoordinatorScopeType.DEPARTMENT.value,
        department_id,
    )


def test_a_deliberately_different_scope_is_left_alone(
    db_settings: Settings, department_id: uuid.UUID, seed_user: Callable[..., SeededUser]
) -> None:
    engine = create_engine(str(db_settings.database_url))
    with engine.begin() as connection:
        elsewhere = connection.execute(
            sa.text(
                "INSERT INTO departments (id, school_id, name) "
                "SELECT :id, school_id, :name FROM departments WHERE id = :dept RETURNING id"
            ),
            {"id": uuid.uuid4(), "name": "Soil Science", "dept": department_id},
        ).scalar_one()
    deliberate = seed_user(
        UserRole.RESEARCH_COORDINATOR,
        department_id=department_id,
        coordinator_scope_type=CoordinatorScopeType.DEPARTMENT,
        coordinator_scope_id=elsewhere,
    )

    _run_backfill(db_settings)

    assert _scope(db_settings, deliberate.id)[1] == elsewhere


def test_nobody_else_is_touched(
    db_settings: Settings, department_id: uuid.UUID, seed_user: Callable[..., SeededUser]
) -> None:
    """A faculty member is not quietly handed a coordinator's authority."""
    member = seed_user(UserRole.FACULTY, department_id=department_id)

    _run_backfill(db_settings)

    assert _scope(db_settings, member.id) == (None, None)


def test_running_it_twice_changes_nothing(
    db_settings: Settings, department_id: uuid.UUID, seed_user: Callable[..., SeededUser]
) -> None:
    stranded = seed_user(UserRole.RESEARCH_COORDINATOR, department_id=department_id)

    _run_backfill(db_settings)
    first = _scope(db_settings, stranded.id)
    _run_backfill(db_settings)

    assert _scope(db_settings, stranded.id) == first
