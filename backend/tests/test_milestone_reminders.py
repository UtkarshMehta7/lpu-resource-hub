"""The milestone reminder job.

The guarantee worth testing is idempotency. The scheduler runs this every
hour by default, and the job itself has no memory -- what stops a milestone
that is three weeks late producing twenty-one identical rows in somebody's
inbox is the dedupe key and the partial unique index behind it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.jobs.reminders import send_milestone_reminders
from app.main import create_app
from app.modules.notifications.models import Notification, NotificationType
from tests.conftest import SeededUser
from tests.world import World, auth, build_world

pytestmark = pytest.mark.db

TODAY = datetime.now(UTC).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def world(client: TestClient, seed_user: Callable[..., SeededUser]) -> World:
    return build_world(client, seed_user)


@pytest.fixture
def session(db_settings: Settings) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db
    engine.dispose()


def add_milestone(client: TestClient, world: World, *, title: str, due: int) -> dict[str, object]:
    body: dict[str, object] = client.post(
        f"/api/v1/projects/{world.project_id}/milestones",
        headers=auth(world.faculty),
        json={"title": title, "due_date": day(due)},
    ).json()
    return body


def count_of(db: Session, kind: NotificationType, user_id: uuid.UUID | None = None) -> int:
    query = (
        select(func.count()).select_from(Notification).where(Notification.notification_type == kind)
    )
    if user_id is not None:
        query = query.where(Notification.user_id == user_id)
    return db.scalar(query) or 0


# --- due soon --------------------------------------------------------------


@pytest.mark.parametrize("lead", [7, 1])
def test_a_milestone_due_at_a_lead_time_is_announced(
    client: TestClient, world: World, session: Session, lead: int
) -> None:
    add_milestone(client, world, title=f"Due in {lead}", due=lead)
    assert send_milestone_reminders(session) >= 1
    assert count_of(session, NotificationType.MILESTONE_DUE, world.faculty.id) == 1


def test_a_milestone_between_lead_times_says_nothing_yet(
    client: TestClient, world: World, session: Session
) -> None:
    """Four days out is neither seven nor one, so it is not yet news."""
    add_milestone(client, world, title="Four days", due=4)
    send_milestone_reminders(session)
    assert count_of(session, NotificationType.MILESTONE_DUE) == 0


def test_the_whole_team_is_told_not_only_the_owner(
    client: TestClient, world: World, session: Session
) -> None:
    client.post(
        f"/api/v1/projects/{world.project_id}/members",
        headers=auth(world.faculty),
        json={"user_id": str(world.student.id), "member_role": "Research assistant"},
    )
    add_milestone(client, world, title="Team deadline", due=7)
    send_milestone_reminders(session)
    assert count_of(session, NotificationType.MILESTONE_DUE, world.faculty.id) == 1
    assert count_of(session, NotificationType.MILESTONE_DUE, world.student.id) == 1


# --- overdue ---------------------------------------------------------------


def test_a_late_milestone_is_reported_once_ever(
    client: TestClient, world: World, session: Session
) -> None:
    """Not once a day for as long as it stays late."""
    add_milestone(client, world, title="Late", due=-10)
    send_milestone_reminders(session)
    send_milestone_reminders(session)
    send_milestone_reminders(session)
    assert count_of(session, NotificationType.MILESTONE_OVERDUE, world.faculty.id) == 1


# --- idempotency and silence ----------------------------------------------


def test_running_the_job_twice_notifies_once(
    client: TestClient, world: World, session: Session
) -> None:
    add_milestone(client, world, title="Due soon", due=7)
    first = send_milestone_reminders(session)
    second = send_milestone_reminders(session)
    assert first == 1
    assert second == 0


def test_finished_work_is_silent(client: TestClient, world: World, session: Session) -> None:
    milestone = add_milestone(client, world, title="Already done", due=-5)
    client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "done"},
    )
    assert send_milestone_reminders(session) == 0


def test_cancelled_work_is_silent(client: TestClient, world: World, session: Session) -> None:
    milestone = add_milestone(client, world, title="Dropped", due=-5)
    client.post(
        f"/api/v1/milestones/{milestone['id']}/status",
        headers=auth(world.faculty),
        json={"status": "cancelled"},
    )
    assert send_milestone_reminders(session) == 0


def test_a_project_with_no_milestones_is_silent(
    client: TestClient, world: World, session: Session
) -> None:
    assert send_milestone_reminders(session) == 0
