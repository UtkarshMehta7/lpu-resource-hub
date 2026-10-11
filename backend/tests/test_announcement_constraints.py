"""The two CHECKs on `announcements`, asserted against the database.

The service always sets `published_at` when it publishes and always derives a
department for a departmental notice, so these constraints are never reached
through the API. That is exactly why they are worth a test of their own: a
constraint nothing exercises is a constraint nobody notices has been dropped,
and both of these are the "a status claiming an event carries that event's
date" rule the milestones and the patent pipeline are held to.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import hash_password
from app.modules.admin.models import Department, School
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementStatus,
)
from app.modules.users.models import User, UserRole

pytestmark = pytest.mark.db


@pytest.fixture
def db(db_settings: Settings, clean_db: None) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def _poster(db: Session) -> User:
    user = User(
        registration_number=f"C{uuid.uuid4().hex[:10]}".upper(),
        email=f"constraint-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("not-used-directly-seeded12"),
        full_name="Constraint Poster",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.flush()
    return user


def _department(db: Session) -> Department:
    school = School(name="School of Constraints")
    db.add(school)
    db.flush()
    department = Department(school_id=school.id, name="Integrity")
    db.add(department)
    db.flush()
    return department


def _notice(poster: User, **overrides: object) -> Announcement:
    fields: dict[str, object] = {
        "subject": "A notice",
        "body": "Body text.",
        "audience": AnnouncementAudience.INSTITUTION,
        "department_id": None,
        "posted_by": poster.id,
        "posted_by_role": poster.role,
        "posted_by_name": poster.full_name,
        "status": AnnouncementStatus.DRAFT,
        "published_at": None,
    }
    fields.update(overrides)
    return Announcement(**fields)


def test_a_published_notice_must_carry_its_date(db: Session) -> None:
    poster = _poster(db)
    db.add(_notice(poster, status=AnnouncementStatus.PUBLISHED, published_at=None))

    with pytest.raises(IntegrityError, match="published_notice_is_dated"):
        db.flush()


def test_a_departmental_notice_must_name_its_department(db: Session) -> None:
    poster = _poster(db)
    db.add(_notice(poster, audience=AnnouncementAudience.DEPARTMENT, department_id=None))

    with pytest.raises(IntegrityError, match="department_notice_names_its_department"):
        db.flush()


def test_a_draft_needs_no_date(db: Session) -> None:
    """The other half of the first rule: only a CLAIM of publication is dated."""
    poster = _poster(db)
    db.add(_notice(poster))

    db.flush()  # no error


def test_an_institution_wide_notice_needs_no_department(db: Session) -> None:
    poster = _poster(db)
    department = _department(db)
    # And naming one anyway is permitted by the CHECK, which only constrains
    # the departmental direction. The service never does it; this records that
    # the database is not what would stop it.
    db.add(_notice(poster, department_id=department.id))

    db.flush()  # no error


def test_deleting_the_department_takes_its_notices(db: Session) -> None:
    """CASCADE, so a departmental notice can never be left addressing nothing.

    Which is also why the audience is derived rather than stored loosely: the
    notice and the department it was addressed to live and die together.
    """
    poster = _poster(db)
    department = _department(db)
    db.add(
        _notice(
            poster,
            audience=AnnouncementAudience.DEPARTMENT,
            department_id=department.id,
            status=AnnouncementStatus.PUBLISHED,
            published_at=text("now()"),
        )
    )
    db.flush()

    db.delete(department)
    db.flush()

    assert db.query(Announcement).count() == 0
