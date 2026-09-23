"""The demo seed script is idempotent and produces the documented counts."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.modules.admin.models import Department, School
from app.modules.profiles.models import (
    ResearcherProfile,
    StudentProfile,
    VerificationStatus,
)
from app.modules.taxonomy.models import ResearchArea, Skill, TagAlias
from app.modules.users.models import User, UserRole
from scripts.seed_demo_data import (
    COORDINATOR_COUNT,
    FACULTY_COUNT,
    STUDENT_COUNT,
    seed,
)

pytestmark = pytest.mark.db

# Argon2 is slow by design; the script hashes once and reuses, and the tests
# don't verify any seeded password, so a placeholder hash is enough here.
PLACEHOLDER_HASH = "$argon2id$v=19$m=65536,t=3,p=4$placeholder$placeholder"


@pytest.fixture
def db(db_settings: Settings, clean_db: None) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    engine.dispose()


def _count(db: Session, model: type) -> int:
    return int(db.execute(select(func.count()).select_from(model)).scalar_one())


def test_seed_creates_the_documented_counts(db: Session) -> None:
    summary = seed(db, PLACEHOLDER_HASH)

    assert _count(db, School) == 3
    assert _count(db, Department) == 8
    assert _count(db, Skill) == 60
    assert _count(db, ResearchArea) == 40
    assert _count(db, TagAlias) == 6
    assert _count(db, User) == FACULTY_COUNT + STUDENT_COUNT + COORDINATOR_COUNT + 1
    assert _count(db, ResearcherProfile) == FACULTY_COUNT
    assert _count(db, StudentProfile) == STUDENT_COUNT
    assert summary.users == FACULTY_COUNT + STUDENT_COUNT + COORDINATOR_COUNT + 1


def test_seed_is_idempotent(db: Session) -> None:
    seed(db, PLACEHOLDER_HASH)
    counts_after_first = {
        model: _count(db, model)
        for model in (School, Department, Skill, ResearchArea, TagAlias, User)
    }

    second_summary = seed(db, PLACEHOLDER_HASH)

    assert {model: _count(db, model) for model in counts_after_first} == counts_after_first
    assert second_summary.users == 0
    assert second_summary.schools == 0
    assert second_summary.profiles == 0


def test_every_seeded_user_is_flagged_as_demo(db: Session) -> None:
    seed(db, PLACEHOLDER_HASH)

    non_demo = db.execute(select(func.count()).select_from(User).where(~User.is_demo)).scalar_one()

    assert non_demo == 0


def test_seed_creates_one_admin_and_scoped_coordinators(db: Session) -> None:
    seed(db, PLACEHOLDER_HASH)

    admins = list(db.execute(select(User).where(User.role == UserRole.ADMIN)).scalars())
    coordinators = list(
        db.execute(select(User).where(User.role == UserRole.RESEARCH_COORDINATOR)).scalars()
    )

    assert len(admins) == 1
    assert len(coordinators) == COORDINATOR_COUNT
    assert all(c.coordinator_scope_id is not None for c in coordinators)


def test_seed_leaves_some_researchers_pending_for_the_queue(db: Session) -> None:
    seed(db, PLACEHOLDER_HASH)

    pending = list(
        db.execute(
            select(ResearcherProfile).where(ResearcherProfile.verification_status == "pending")
        ).scalars()
    )

    assert len(pending) > 0


def test_the_documented_demo_faculty_account_is_verified(db: Session) -> None:
    """DEMOFACULTY01 is the faculty login in the README and the browser flows.

    An unverified researcher can't submit a project or post an opening, so if
    this account seeds as PENDING the whole faculty journey is closed on a
    fresh install -- which is exactly how the end-to-end suite failed.
    """
    seed(db, PLACEHOLDER_HASH)

    profile = db.execute(
        select(ResearcherProfile)
        .join(User, User.id == ResearcherProfile.user_id)
        .where(User.registration_number == "DEMOFACULTY01")
    ).scalar_one()

    assert profile.verification_status is VerificationStatus.VERIFIED


def test_some_profiles_stay_pending_for_the_verification_queue(db: Session) -> None:
    seed(db, PLACEHOLDER_HASH)

    pending = db.execute(
        select(func.count())
        .select_from(ResearcherProfile)
        .where(ResearcherProfile.verification_status == VerificationStatus.PENDING)
    ).scalar_one()

    assert pending > 0
