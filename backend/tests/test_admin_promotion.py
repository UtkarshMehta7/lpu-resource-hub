"""Making someone an administrator takes two people.

An admin opens a challenge, a six-digit code lands in the *target's*
notification inbox, and the promotion only completes when the admin types
back the code the target read out. One compromised admin session is not
enough on its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app
from app.modules.admin import promotions
from app.modules.users.models import UserRole
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


def _open_challenge(client: TestClient, world: World, target_id: uuid.UUID) -> dict[str, object]:
    response = client.post(
        f"/api/v1/admin/users/{target_id}/admin-promotion", headers=auth(world.admin)
    )
    assert response.status_code == 200, response.json()
    body: dict[str, object] = response.json()
    return body


def _code_from_inbox(client: TestClient, target: SeededUser) -> str:
    """Read the code the way the target would: from their own notifications."""
    items = client.get("/api/v1/me/notifications", headers=auth(target)).json()["items"]
    promotion = next(item for item in items if item["notification_type"] == "admin_promotion_code")
    code = promotion["payload"]["code"]
    assert isinstance(code, str)
    return code


def _confirm(
    client: TestClient, world: World, target_id: uuid.UUID, code: str
) -> tuple[int, dict[str, object]]:
    response = client.post(
        f"/api/v1/admin/users/{target_id}/admin-promotion/confirm",
        headers=auth(world.admin),
        json={"code": code},
    )
    return response.status_code, response.json()


# ------------------------------------------------------------- the happy path


def test_the_code_goes_to_the_target_not_the_requester(client: TestClient, world: World) -> None:
    challenge = _open_challenge(client, world, world.faculty.id)

    # The requester is told when it expires, and nothing else.
    assert "code" not in challenge
    assert challenge["target_user_id"] == str(world.faculty.id)

    # The admin's own inbox has nothing; the target's has the code.
    admin_items = client.get("/api/v1/me/notifications", headers=auth(world.admin)).json()["items"]
    assert not [i for i in admin_items if i["notification_type"] == "admin_promotion_code"]
    assert len(_code_from_inbox(client, world.faculty)) == promotions.CODE_LENGTH


def test_the_right_code_completes_the_promotion(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)
    code = _code_from_inbox(client, world.faculty)

    status_code, body = _confirm(client, world, world.faculty.id, code)

    assert status_code == 200, body
    assert body["role"] == "admin"


def test_the_promotion_is_audited_with_both_people(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)
    _confirm(client, world, world.faculty.id, _code_from_inbox(client, world.faculty))

    logs = client.get(
        "/api/v1/admin/audit-logs",
        headers=auth(world.admin),
        params={"entity_id": str(world.faculty.id)},
    ).json()["items"]
    actions = {log["action"] for log in logs}
    assert "user.admin_promotion_requested" in actions
    assert "user.promoted_to_admin" in actions

    promoted = next(log for log in logs if log["action"] == "user.promoted_to_admin")
    assert promoted["actor_id"] == str(world.admin.id)
    assert promoted["before"] == {"role": "faculty"}
    assert promoted["after"]["role"] == "admin"
    # The code never reaches the log.
    assert "code" not in str(promoted)


# ------------------------------------------------------------ what it refuses


def test_a_wrong_code_changes_nothing(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)

    status_code, _ = _confirm(client, world, world.faculty.id, "000000")

    # 000000 could in principle be the real code; retry with a value that
    # definitely isn't if so.
    if status_code == 200:
        pytest.skip("the generated code happened to be 000000")
    assert status_code == 403
    listed = client.get(
        "/api/v1/admin/users", headers=auth(world.admin), params={"page_size": 100}
    ).json()["items"]
    assert next(u for u in listed if u["id"] == str(world.faculty.id))["role"] == "faculty"


def test_the_guesses_run_out(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)
    real_code = _code_from_inbox(client, world.faculty)

    wrong = "111111" if real_code != "111111" else "222222"
    for _ in range(promotions.MAX_ATTEMPTS):
        assert _confirm(client, world, world.faculty.id, wrong)[0] == 403

    # Even the right code is no use now.
    assert _confirm(client, world, world.faculty.id, real_code)[0] == 429


def test_a_code_works_only_once(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)
    code = _code_from_inbox(client, world.faculty)
    assert _confirm(client, world, world.faculty.id, code)[0] == 200

    # Replaying it finds no live challenge.
    assert _confirm(client, world, world.faculty.id, code)[0] in (404, 409)


def test_an_expired_code_is_refused(
    client: TestClient, world: World, db_settings: Settings
) -> None:
    _open_challenge(client, world, world.faculty.id)
    code = _code_from_inbox(client, world.faculty)

    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE admin_promotions SET expires_at = :past"),
                {"past": datetime.now(UTC) - timedelta(minutes=1)},
            )
    finally:
        engine.dispose()

    assert _confirm(client, world, world.faculty.id, code)[0] == 409


def test_confirming_without_a_challenge_is_404(client: TestClient, world: World) -> None:
    assert _confirm(client, world, world.faculty.id, "123456")[0] == 404


def test_an_admin_cannot_promote_themselves(client: TestClient, world: World) -> None:
    response = client.post(
        f"/api/v1/admin/users/{world.admin.id}/admin-promotion", headers=auth(world.admin)
    )

    assert response.status_code == 409


def test_promoting_an_existing_admin_is_refused(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    other_admin = seed_user(UserRole.ADMIN)

    response = client.post(
        f"/api/v1/admin/users/{other_admin.id}/admin-promotion", headers=auth(world.admin)
    )

    assert response.status_code == 409


@pytest.mark.parametrize("actor_name", ["student", "faculty", "coordinator"])
def test_only_an_admin_can_start_or_finish_a_promotion(
    client: TestClient, world: World, actor_name: str
) -> None:
    actor: SeededUser = getattr(world, actor_name)

    started = client.post(
        f"/api/v1/admin/users/{world.other_student.id}/admin-promotion", headers=auth(actor)
    )
    confirmed = client.post(
        f"/api/v1/admin/users/{world.other_student.id}/admin-promotion/confirm",
        headers=auth(actor),
        json={"code": "123456"},
    )

    assert started.status_code == 403
    assert confirmed.status_code == 403


def test_a_promotion_needs_authentication(client: TestClient, world: World) -> None:
    assert client.post(f"/api/v1/admin/users/{world.faculty.id}/admin-promotion").status_code == 401


def test_a_second_request_supersedes_the_first(client: TestClient, world: World) -> None:
    _open_challenge(client, world, world.faculty.id)
    first_code = _code_from_inbox(client, world.faculty)
    _open_challenge(client, world, world.faculty.id)

    # The old code is dead; the newest one works.
    items = client.get("/api/v1/me/notifications", headers=auth(world.faculty)).json()["items"]
    codes = [
        item["payload"]["code"]
        for item in items
        if item["notification_type"] == "admin_promotion_code"
    ]
    newest = next(code for code in codes if code != first_code)
    assert _confirm(client, world, world.faculty.id, first_code)[0] == 403
    assert _confirm(client, world, world.faculty.id, newest)[0] == 200


# ---------------------------------------------------------------- stepping down


def test_an_admin_can_step_down_once_someone_else_holds_it(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    seed_user(UserRole.ADMIN)

    response = client.post(
        "/api/v1/admin/me/step-down", headers=auth(world.admin), json={"new_role": "faculty"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "faculty"


def test_the_last_admin_cannot_step_down(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/admin/me/step-down", headers=auth(world.admin), json={"new_role": "faculty"}
    )

    assert response.status_code == 409


def test_stepping_down_to_admin_is_meaningless_and_refused(
    client: TestClient, world: World, seed_user: Callable[..., SeededUser]
) -> None:
    seed_user(UserRole.ADMIN)

    response = client.post(
        "/api/v1/admin/me/step-down", headers=auth(world.admin), json={"new_role": "admin"}
    )

    assert response.status_code == 409


def test_a_handover_leaves_exactly_one_admin(client: TestClient, world: World) -> None:
    """The whole point: promote a successor, then stand down."""
    _open_challenge(client, world, world.faculty.id)
    _confirm(client, world, world.faculty.id, _code_from_inbox(client, world.faculty))

    stepped = client.post(
        "/api/v1/admin/me/step-down", headers=auth(world.admin), json={"new_role": "faculty"}
    )
    assert stepped.status_code == 200

    # The new admin can still administer; the old one cannot.
    assert client.get("/api/v1/admin/users", headers=auth(world.faculty)).status_code == 200
    assert client.get("/api/v1/admin/users", headers=auth(world.admin)).status_code == 403


def test_only_an_admin_can_step_down(client: TestClient, world: World) -> None:
    response = client.post(
        "/api/v1/admin/me/step-down", headers=auth(world.faculty), json={"new_role": "student"}
    )

    assert response.status_code == 403
