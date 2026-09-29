"""An administrator's profile is not something anyone here signs off.

Verification means somebody senior vouched for a researcher's record. Nobody
is senior to an administrator, so a PENDING administrator was asking a
coordinator to vouch for their own senior -- and the queue had no role filter,
so they really did show up there.

Four guards, because one alone would leave a gap: the profile verifies itself
on save, the queue excludes administrators whatever their stored status, the
verify action refuses them outright, and an import does not send them back.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.imports import service as import_service
from app.modules.users.models import UserRole
from tests.conftest import SeededUser
from tests.test_profile_import_api import ORCID, fake_sources, paper
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


def save_admin_profile(client: TestClient, world: World) -> dict[str, object]:
    response = client.put(
        "/api/v1/me/profile",
        headers=auth(world.admin),
        json={"designation": "Registrar", "bio": "Runs the platform."},
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


# --- saving ----------------------------------------------------------------


def test_an_administrator_saving_a_profile_is_verified_immediately(
    client: TestClient, world: World
) -> None:
    assert save_admin_profile(client, world)["verification_status"] == "verified"


def test_an_administrator_can_keep_editing_without_losing_it(
    client: TestClient, world: World
) -> None:
    save_admin_profile(client, world)
    again = client.put(
        "/api/v1/me/profile",
        headers=auth(world.admin),
        json={"designation": "Registrar", "bio": "Edited again."},
    ).json()
    assert again["verification_status"] == "verified"


def test_everybody_else_still_needs_verifying(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    """The exemption is for administrators only, not a hole for every role.

    A fresh faculty account, not world.other_faculty -- that one is verified
    during setup, and an already-verified profile deliberately keeps its
    status when edited.
    """
    newcomer = seed_user(UserRole.FACULTY, department_id=world.department_id)
    response = client.put(
        "/api/v1/me/profile",
        headers=auth(newcomer),
        json={"designation": "Professor", "bio": "Ordinary researcher."},
    )
    assert response.json()["verification_status"] == "pending"


# --- the queue -------------------------------------------------------------


def test_an_administrator_never_appears_in_a_coordinators_queue(
    client: TestClient, world: World
) -> None:
    save_admin_profile(client, world)
    queue = client.get(
        "/api/v1/coordinator/verification-queue", headers=auth(world.coordinator)
    ).json()
    assert str(world.admin.id) not in {item["user_id"] for item in queue}


def test_an_administrator_left_pending_by_an_older_version_is_still_hidden(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    """Belt and braces: the queue filters on role, not only on saved status."""
    from sqlalchemy import create_engine, text

    save_admin_profile(client, world)
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE researcher_profiles SET verification_status = 'pending' "
                    "WHERE user_id = :uid"
                ),
                {"uid": world.admin.id},
            )
    finally:
        engine.dispose()

    queue = client.get(
        "/api/v1/coordinator/verification-queue", headers=auth(world.coordinator)
    ).json()
    assert str(world.admin.id) not in {item["user_id"] for item in queue}


# --- the action ------------------------------------------------------------


def test_a_coordinator_cannot_verify_an_administrator(client: TestClient, world: World) -> None:
    save_admin_profile(client, world)
    response = client.post(
        f"/api/v1/researchers/{world.admin.id}/verify",
        headers=auth(world.coordinator),
        json={"decision": "verified"},
    )
    assert response.status_code == 409


def test_a_coordinator_cannot_reject_an_administrator_either(
    client: TestClient, world: World
) -> None:
    """The dangerous half: rejecting would strip a senior's standing."""
    save_admin_profile(client, world)
    response = client.post(
        f"/api/v1/researchers/{world.admin.id}/verify",
        headers=auth(world.coordinator),
        json={"decision": "rejected", "comment": "No."},
    )
    assert response.status_code == 409


def test_another_administrator_cannot_verify_one_either(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    save_admin_profile(client, world)
    other_admin = seed_user(UserRole.ADMIN)
    response = client.post(
        f"/api/v1/researchers/{world.admin.id}/verify",
        headers=auth(other_admin),
        json={"decision": "verified"},
    )
    assert response.status_code == 409


def test_verifying_an_ordinary_researcher_still_works(client: TestClient, world: World) -> None:
    client.put(
        "/api/v1/me/profile",
        headers=auth(world.other_faculty),
        json={"designation": "Professor", "bio": "Ordinary researcher."},
    )
    response = client.post(
        f"/api/v1/researchers/{world.other_faculty.id}/verify",
        headers=auth(world.coordinator),
        json={"decision": "verified"},
    )
    assert response.status_code == 200


# --- importing -------------------------------------------------------------


def test_an_import_does_not_send_an_administrator_back_for_review(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the import would put them in a queue nobody may act on."""
    save_admin_profile(client, world)
    monkeypatch.setattr(
        import_service, "_gather", fake_sources(paper("Admin paper", doi="10.1234/admin"))
    )
    preview = client.post(
        "/api/v1/me/profile/import/preview", headers=auth(world.admin), json={"orcid": ORCID}
    ).json()
    result = client.post(
        "/api/v1/me/profile/import",
        headers=auth(world.admin),
        json={"orcid": ORCID, "fields": ["bio"], "work_keys": [preview["works"][0]["key"]]},
    ).json()

    assert result["verification_reset"] is False
    after = client.get("/api/v1/me/profile", headers=auth(world.admin)).json()
    assert after["verification_status"] == "verified"
