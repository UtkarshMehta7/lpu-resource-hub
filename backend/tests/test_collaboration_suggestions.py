"""Collaboration suggestion notifications (§11).

The suggestion worth sending is the *gap*: two people whose expertise overlaps
and who have never published together. These drive the job directly rather
than through the API, because it is a scheduled pass with no endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.notifications.collaboration_suggestions import (
    send_collaboration_suggestions,
)
from app.modules.notifications.models import Notification, NotificationType
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture
def db(db_settings: Settings) -> Iterator[Session]:
    engine = create_engine(str(db_settings.database_url))
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def auth(user: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.access_token}"}


def give_expertise(client: TestClient, user: SeededUser, skill_ids: list[str]) -> None:
    client.put(
        "/api/v1/me/profile",
        headers=auth(user),
        json={"designation": "Professor", "bio": "Soil moisture sensing for farms."},
    )
    response = client.put(
        "/api/v1/me/skills",
        headers=auth(user),
        json=[{"skill_id": skill_id, "proficiency": 5} for skill_id in skill_ids],
    )
    assert response.status_code in (200, 204), response.text


@pytest.fixture
def skills(client: TestClient, seed_user: Callable[..., SeededUser]) -> list[str]:
    coordinator = seed_user(UserRole.RESEARCH_COORDINATOR)
    ids = []
    for name in ("Soil Sensing", "Remote Sensing", "Hydrology", "Signal Processing"):
        created = client.post(
            "/api/v1/taxonomy/skills", headers=auth(coordinator), json={"name": name}
        )
        assert created.status_code in (200, 201), created.text
        ids.append(created.json()["id"])
    return ids


def suggestions_for(db: Session, user_id: object) -> list[Notification]:
    return list(
        db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.notification_type == NotificationType.COLLABORATION_SUGGESTION,
            )
        ).scalars()
    )


def test_two_people_with_overlapping_expertise_are_introduced(
    client: TestClient,
    db: Session,
    skills: list[str],
    seed_user: Callable[..., SeededUser],
) -> None:
    one = seed_user(UserRole.FACULTY)
    two = seed_user(UserRole.FACULTY)
    give_expertise(client, one, skills)
    give_expertise(client, two, skills)

    sent = send_collaboration_suggestions(db)
    db.commit()

    assert sent >= 1
    introduced = suggestions_for(db, one.id) + suggestions_for(db, two.id)
    assert introduced
    payload = introduced[0].payload
    assert payload["full_name"]
    # Names collide; the registration number is what tells two apart.
    assert payload["registration_number"]
    # Reasons come from the score breakdown, never from generated prose.
    assert payload["reasons"]


def test_a_pairing_is_only_ever_suggested_once(
    client: TestClient,
    db: Session,
    skills: list[str],
    seed_user: Callable[..., SeededUser],
) -> None:
    """The dedupe key is the ordered pair, so running the job weekly does not
    reintroduce the same two people every week."""
    one = seed_user(UserRole.FACULTY)
    two = seed_user(UserRole.FACULTY)
    give_expertise(client, one, skills)
    give_expertise(client, two, skills)

    send_collaboration_suggestions(db)
    db.commit()
    before = len(suggestions_for(db, one.id)) + len(suggestions_for(db, two.id))
    send_collaboration_suggestions(db)
    db.commit()
    after = len(suggestions_for(db, one.id)) + len(suggestions_for(db, two.id))

    assert before >= 1
    assert after == before


def test_existing_co_authors_are_never_suggested_to_each_other(
    client: TestClient,
    db: Session,
    skills: list[str],
    seed_user: Callable[..., SeededUser],
) -> None:
    """The point of the suggestion is the gap. Two people already on the same
    paper have demonstrably found each other."""
    one = seed_user(UserRole.FACULTY)
    two = seed_user(UserRole.FACULTY)
    give_expertise(client, one, skills)
    give_expertise(client, two, skills)
    published = client.post(
        "/api/v1/publications",
        headers=auth(one),
        json={
            "title": "Joint field trials of soil moisture sensors",
            "year": 2025,
            "pub_type": "journal_article",
            "authors": [{"user_id": str(one.id)}, {"user_id": str(two.id)}],
        },
    )
    assert published.status_code == 201, published.text

    send_collaboration_suggestions(db)
    db.commit()

    for person, other in ((one, two), (two, one)):
        for notification in suggestions_for(db, person.id):
            assert notification.payload["user_id"] != str(other.id)


def test_somebody_with_no_expertise_is_neither_told_nor_suggested(
    client: TestClient,
    db: Session,
    skills: list[str],
    seed_user: Callable[..., SeededUser],
) -> None:
    """Below the tag floor `recommend` returns its cold-start list -- the
    newest people, which is a listing and not a suggestion. Sending that would
    be worse than silence."""
    bare = seed_user(UserRole.FACULTY)

    send_collaboration_suggestions(db)
    db.commit()

    assert suggestions_for(db, bare.id) == []
