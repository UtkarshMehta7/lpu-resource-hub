"""A registration number identifies exactly one person, everywhere.

It is what everyone signs in with, so two accounts sharing one — even in
different case — would mean two people answering to the same identity. The
guarantee has three parts, and this pins all three:

1. the column is UNIQUE in the database,
2. every write path upper-cases before storing, so case cannot be used to
   slip past that index,
3. every entry point that creates a user goes through one of those paths.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.db.model_registry  # noqa: F401  registers every table
from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app
from app.modules.auth.schemas import normalise_registration_number
from app.modules.users.models import User, UserRole
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


def _create(client: TestClient, creator: SeededUser, registration_number: str) -> int:
    return client.post(
        "/api/v1/users",
        headers=auth(creator),
        json={"registration_number": registration_number, "full_name": "Someone"},
    ).status_code


# ------------------------------------------------------------ the write paths


def test_the_same_number_twice_is_refused(client: TestClient, world: World) -> None:
    assert _create(client, world.faculty, "12400942") == 201
    assert _create(client, world.faculty, "12400942") == 409


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("ab12cd34", "AB12CD34"),  # lower then upper
        ("AB12CD34", "ab12cd34"),  # upper then lower
        ("Ab12Cd34", "aB12cD34"),  # mixed both ways
    ],
)
def test_case_cannot_be_used_to_duplicate_a_number(
    client: TestClient, world: World, first: str, second: str
) -> None:
    """The index is on the stored value, so normalisation is what makes the
    uniqueness case-insensitive. If a path ever stops upper-casing, this
    fails rather than silently admitting a twin."""
    assert _create(client, world.faculty, first) == 201
    assert _create(client, world.faculty, second) == 409


def test_surrounding_whitespace_is_not_a_new_person(client: TestClient, world: World) -> None:
    assert _create(client, world.faculty, "77798511") == 201
    assert _create(client, world.faculty, "  77798511  ") == 409


def test_the_admin_override_shares_the_same_guarantee(client: TestClient, world: World) -> None:
    """A second door must not be a second namespace."""
    assert _create(client, world.faculty, "override01") == 201

    response = client.post(
        "/api/v1/admin/users",
        headers=auth(world.admin),
        json={
            "registration_number": "OVERRIDE01",
            "full_name": "The Same Number",
            "role": "faculty",
            "department_id": world.department_id,
        },
    )

    assert response.status_code == 409


def test_what_is_stored_is_always_upper_case(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    assert _create(client, world.faculty, "mixedCase12") == 201

    engine = create_engine(str(db_settings.database_url))
    try:
        with sessionmaker(bind=engine)() as db:
            stored = db.execute(
                select(User.registration_number).where(
                    func.upper(User.registration_number) == "MIXEDCASE12"
                )
            ).scalar_one()
    finally:
        engine.dispose()

    assert stored == "MIXEDCASE12"


# --------------------------------------------------------- the database itself


def test_the_database_refuses_a_duplicate_even_without_the_api(
    db_settings: Settings, clean_db: None
) -> None:
    """The last line of defence: a UNIQUE index, not application logic. A new
    write path added later inherits this whether or not it remembers to
    check."""
    engine = create_engine(str(db_settings.database_url))
    session_factory = sessionmaker(bind=engine)
    try:
        with session_factory() as db:
            db.add(
                User(
                    registration_number="DIRECT0001",
                    password_hash=hash_password("not-used-directly-seeded12"),
                    full_name="First",
                    role=UserRole.STUDENT,
                )
            )
            db.commit()

        with session_factory() as db, pytest.raises(IntegrityError):
            db.add(
                User(
                    registration_number="DIRECT0001",
                    password_hash=hash_password("not-used-directly-seeded12"),
                    full_name="Second",
                    role=UserRole.STUDENT,
                )
            )
            db.commit()
    finally:
        engine.dispose()


def test_normalisation_is_one_shared_function() -> None:
    """Every path calls this, so the rule lives in one place."""
    assert normalise_registration_number("  ab12cd34 ") == "AB12CD34"
    assert normalise_registration_number("AB12CD34") == "AB12CD34"
