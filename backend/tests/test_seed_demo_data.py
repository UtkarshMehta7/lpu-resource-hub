"""The demo seed script is idempotent and produces the documented counts."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.modules.admin.models import Department, School
from app.modules.facilities.models import Equipment, Facility
from app.modules.profiles.models import (
    ResearcherProfile,
    StudentProfile,
    VerificationStatus,
)
from app.modules.taxonomy.models import ResearchArea, Skill, TagAlias
from app.modules.users.models import User, UserRole
from scripts.seed_demo_data import (
    COORDINATOR_COUNT,
    DEMO_EQUIPMENT,
    DEMO_FACILITIES,
    FACULTY_COUNT,
    STUDENT_COUNT,
    _demo_registration_number,
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
    # +1 admin, +1 custodian, +1 dean -- the two roles outside the chain.
    assert _count(db, User) == FACULTY_COUNT + STUDENT_COUNT + COORDINATOR_COUNT + 3
    assert _count(db, ResearcherProfile) == FACULTY_COUNT
    assert _count(db, StudentProfile) == STUDENT_COUNT
    assert summary.users == FACULTY_COUNT + STUDENT_COUNT + COORDINATOR_COUNT + 3
    assert _count(db, Facility) == len(DEMO_FACILITIES)
    assert _count(db, Equipment) == len(DEMO_FACILITIES) * len(DEMO_EQUIPMENT)


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
    """The faculty login in the README and the browser flows.

    An unverified researcher can't submit a project or post an opening, so if
    this account seeds as PENDING the whole faculty journey is closed on a
    fresh install -- which is exactly how the end-to-end suite failed.

    The number is derived rather than written out, so renumbering the demo
    accounts cannot leave this test asserting against an identifier that no
    longer exists -- which is how it broke when they became LPU-shaped.
    """
    seed(db, PLACEHOLDER_HASH)

    registration_number = _demo_registration_number("demo.faculty01@example.com")
    profile = db.execute(
        select(ResearcherProfile)
        .join(User, User.id == ResearcherProfile.user_id)
        .where(User.registration_number == registration_number)
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


def test_seed_creates_the_two_roles_outside_the_provisioning_chain(db: Session) -> None:
    """Without these, neither role can be signed in as on a fresh install.

    A role nobody can sign in as cannot be shown to work, which is how the
    custodian shipped enforced but unassignable.
    """
    seed(db, PLACEHOLDER_HASH)

    custodian = db.execute(
        select(User).where(User.role == UserRole.FACILITY_CUSTODIAN)
    ).scalar_one()
    dean = db.execute(select(User).where(User.role == UserRole.DEAN_OF_RESEARCH)).scalar_one()

    assert custodian.registration_number == _demo_registration_number(
        "demo.custodian01@example.com"
    )
    assert dean.registration_number == _demo_registration_number("demo.dean01@example.com")
    # A custodian belongs to a department; a dean reads the whole institution
    # and must not, or INSTITUTION_WIDE_ROLES means nothing.
    assert custodian.department_id is not None
    assert dean.department_id is None


def test_the_seeded_custodian_actually_holds_a_facility(db: Session) -> None:
    """The point of seeding the role at all.

    An unassigned custodian has an empty scope, so every screen the role
    reaches would be empty and the demo would show nothing.
    """
    seed(db, PLACEHOLDER_HASH)

    custodian = db.execute(
        select(User).where(User.role == UserRole.FACILITY_CUSTODIAN)
    ).scalar_one()
    held = list(db.execute(select(Facility).where(Facility.custodian_id == custodian.id)).scalars())

    assert len(held) == 1
    # And the room has something bookable in it, or the booking queue is empty.
    in_room = db.execute(
        select(func.count()).select_from(Equipment).where(Equipment.facility_id == held[0].id)
    ).scalar_one()
    assert int(in_room) == len(DEMO_EQUIPMENT)
    # Same department as the facility it looks after -- the rule the API
    # enforces on assignment, so the seed must not contradict it.
    assert custodian.department_id == held[0].department_id
