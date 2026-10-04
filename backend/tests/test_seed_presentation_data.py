"""The presentation seed, and the invariant it broke against production.

`seed_presentation_data.py` matches people on registration number and updates
what it finds. Run against the deployed database it matched a number that
already belonged to a research coordinator, changed the role to facility
custodian, and left the old `coordinator_scope_id` on the row -- a
non-coordinator carrying a coordinator scope, which is exactly what
`_sync_coordinator_scope` exists to prevent in the application.

Nothing in the application could have caused that; only a script writing to
the side could. So the guard belongs here.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.modules.admin.models import Department, School
from app.modules.facilities.models import Facility
from app.modules.milestones.risk import Risk, RiskInput, assess
from app.modules.users.models import CoordinatorScopeType, User, UserRole
from scripts.seed_presentation_data import (
    MILESTONE_SHAPES,
    Person,
    Summary,
    _get_or_create_user,
    seed,
)

pytestmark = pytest.mark.db


@pytest.fixture
def db(db_settings: Settings, clean_db: None) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def _department(db: Session) -> Department:
    school = School(name="School of Computer Science and Engineering")
    db.add(school)
    db.flush()
    department = Department(school_id=school.id, name="Computer Science and Engineering")
    db.add(department)
    db.flush()
    return department


def test_changing_somebody_to_a_non_coordinator_clears_their_scope(db: Session) -> None:
    """The production bug, reproduced.

    Seed a coordinator, then seed the same registration number as a facility
    custodian -- which is what happened when the custodian numbers collided
    with an account that was already there.
    """
    department = _department(db)
    summary = Summary()
    person = Person("Gurpreet Dhillon", "12400401")

    coordinator = _get_or_create_user(
        db,
        person=person,
        role=UserRole.RESEARCH_COORDINATOR,
        department=department,
        summary=summary,
    )
    assert coordinator.coordinator_scope_id == department.id

    converted = _get_or_create_user(
        db,
        person=person,
        role=UserRole.FACILITY_CUSTODIAN,
        department=department,
        summary=summary,
    )

    assert converted.id == coordinator.id, "same registration number, same row"
    assert converted.role is UserRole.FACILITY_CUSTODIAN
    assert converted.coordinator_scope_id is None
    assert converted.coordinator_scope_type is None


def test_a_dean_never_acquires_a_scope_or_a_department(db: Session) -> None:
    summary = Summary()
    dean = _get_or_create_user(
        db,
        person=Person("Vikram Chopra", "12400501"),
        role=UserRole.DEAN_OF_RESEARCH,
        department=None,
        summary=summary,
    )

    assert dean.department_id is None
    assert dean.coordinator_scope_id is None
    assert dean.coordinator_scope_type is None


def test_a_coordinator_still_gets_their_scope(db: Session) -> None:
    department = _department(db)
    summary = Summary()

    coordinator = _get_or_create_user(
        db,
        person=Person("Rajesh Khanna", "12400101"),
        role=UserRole.RESEARCH_COORDINATOR,
        department=department,
        summary=summary,
    )

    assert coordinator.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
    assert coordinator.coordinator_scope_id == department.id


def test_a_full_seed_leaves_no_scope_on_a_non_coordinator(db: Session) -> None:
    """The invariant stated over the whole result, not one helper call."""
    seed(db)

    stray = db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.role != UserRole.RESEARCH_COORDINATOR,
            User.coordinator_scope_id.is_not(None),
        )
    ).scalar_one()
    assert stray == 0


def test_a_full_seed_puts_every_facility_in_somebody_s_care(db: Session) -> None:
    """A facility reading 'nobody looks after this yet' in a demonstration
    looks like a gap rather than a deliberate state."""
    seed(db)

    total = db.execute(select(func.count()).select_from(Facility)).scalar_one()
    held = db.execute(
        select(func.count()).select_from(Facility).where(Facility.custodian_id.is_not(None))
    ).scalar_one()
    assert total > 0
    assert held == total

    # And every assignment satisfies the rule the API enforces: a custodian
    # belongs to the department that runs the facility.
    wrong = db.execute(
        select(func.count())
        .select_from(Facility)
        .join(User, User.id == Facility.custodian_id)
        .where(User.department_id != Facility.department_id)
    ).scalar_one()
    assert wrong == 0


def test_the_milestone_shapes_between_them_show_every_risk_state() -> None:
    """The board must be able to show the state it is named after.

    The first version of this seed gave every project the same chain, with an
    overdue milestone in front of the rest. `blocked` beats `at_risk`
    (ADR 0026), so the deployed instance reported at_risk: 0 and on_track: 0 --
    the at-risk board demonstrating neither.

    Asserted against the real `assess`, not against reasoning about it.
    """
    from datetime import date, timedelta

    today = date.today()
    threshold = 7
    seen: set[Risk] = set()

    for _name, plan in MILESTONE_SHAPES:
        inputs = [
            RiskInput(status=status, due_date=today + timedelta(days=offset))
            for _title, offset, status in plan
        ]
        for position, milestone in enumerate(inputs):
            # Each milestone waits on the one before it, as the seed wires it.
            depends_on = [inputs[position - 1]] if position else []
            seen.add(
                assess(milestone, today=today, threshold_days=threshold, depends_on=depends_on)
            )

    assert Risk.AT_RISK in seen, "no shape produces an at-risk milestone"
    assert Risk.ON_TRACK in seen, "no shape produces an on-track milestone"
    assert Risk.OVERDUE in seen
    assert Risk.BLOCKED in seen
    assert Risk.NONE in seen


def test_a_full_seed_leaves_milestones_in_more_than_one_risk_state(db: Session) -> None:
    """The property over real rows: an adherence panel of a single state is
    not a demonstration of anything."""
    from datetime import date

    from app.modules.milestones.models import Milestone

    seed(db)
    milestones = list(db.execute(select(Milestone)).scalars())
    assert milestones

    today = date.today()
    states = {
        assess(RiskInput(status=m.status, due_date=m.due_date), today=today, threshold_days=7)
        for m in milestones
    }
    # Ignoring dependencies here: this is about the dates themselves spanning
    # the range, which is what the shapes are for.
    assert Risk.AT_RISK in states
    assert Risk.ON_TRACK in states
    assert Risk.OVERDUE in states
