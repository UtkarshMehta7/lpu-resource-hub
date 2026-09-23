"""Auth + users integration tests against a real PostgreSQL database.

Requires TEST_DATABASE_URL (skipped otherwise, see conftest.py). Each test
runs against freshly truncated `users`/`refresh_tokens` tables (the `clean_db`
fixture) so tests do not see each other's rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app

pytestmark = pytest.mark.db

# Faculty self-register; students are created for them (ADR 0015). The
# registration number is what you log in with, email is optional contact.
REGISTER_PAYLOAD = {
    "registration_number": "demo123456",
    "email": "Faculty1@Example.com",
    "password": "correcthorsebattery",
    "full_name": "Faculty One",
    "role": "faculty",
}
LOGIN_PAYLOAD = {"registration_number": "DEMO123456", "password": "correcthorsebattery"}


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        # Real (JS-driven) clients always send this; tests that specifically
        # exercise the CSRF defence build their own client without it.
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


def _register(client: TestClient, **overrides: object) -> Response:
    payload = {**REGISTER_PAYLOAD, **overrides}
    return client.post("/api/v1/auth/register", json=payload)


def test_register_creates_user_and_sets_refresh_cookie(client: TestClient) -> None:
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["registration_number"] == "DEMO123456"  # normalised to upper case
    assert body["user"]["email"] == "faculty1@example.com"  # normalised to lowercase
    assert body["user"]["role"] == "faculty"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert body["token_type"] == "bearer"
    assert response.cookies.get("refresh_token") is not None


def test_register_rejects_duplicate_registration_number(client: TestClient) -> None:
    _register(client)

    response = _register(client, full_name="Someone Else")

    assert response.status_code == 409


def test_register_rejects_a_registration_number_differing_only_by_case(
    client: TestClient,
) -> None:
    _register(client)

    response = _register(client, registration_number="DEMO123456", email="other@example.com")

    assert response.status_code == 409


@pytest.mark.parametrize("role", ["admin", "research_coordinator"])
def test_register_rejects_non_self_registerable_roles(client: TestClient, role: str) -> None:
    response = _register(client, role=role)

    assert response.status_code == 422


def test_login_succeeds_with_correct_credentials(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/api/v1/auth/login",
        json=LOGIN_PAYLOAD,
    )

    assert response.status_code == 200
    assert response.cookies.get("refresh_token") is not None


def test_login_fails_with_wrong_password(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_failure_message_is_identical_for_unknown_account_and_wrong_password(
    client: TestClient,
) -> None:
    """No user enumeration: registration numbers are sequential and semi-public,
    so an unknown one and a wrong password must look identical."""
    _register(client)

    unknown_account = client.post(
        "/api/v1/auth/login",
        json={"registration_number": "NOBODY000", "password": "whatever12345"},
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "wrong-password"},
    )

    assert unknown_account.status_code == wrong_password.status_code == 401
    assert unknown_account.json() == wrong_password.json()


def test_users_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_users_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_users_me_returns_the_authenticated_profile(client: TestClient) -> None:
    access_token = _register(client).json()["access_token"]

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["registration_number"] == "DEMO123456"


def test_refresh_issues_a_usable_access_token_and_rotates_the_refresh_cookie(
    client: TestClient,
) -> None:
    _register(client)
    old_refresh_cookie = client.cookies.get("refresh_token")

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    new_access_token = response.json()["access_token"]
    assert client.cookies.get("refresh_token") != old_refresh_cookie

    me_response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_response.status_code == 200


def test_reusing_a_rotated_out_refresh_token_revokes_the_whole_family(
    client: TestClient,
) -> None:
    _register(client)
    old_refresh_cookie = client.cookies.get("refresh_token")
    assert old_refresh_cookie is not None

    first_refresh = client.post("/api/v1/auth/refresh")
    assert first_refresh.status_code == 200
    new_refresh_cookie = client.cookies.get("refresh_token")
    assert new_refresh_cookie != old_refresh_cookie

    # Present the OLD (already rotated-out) token again: reuse detected.
    client.cookies.set("refresh_token", old_refresh_cookie)
    reuse_response = client.post("/api/v1/auth/refresh")
    assert reuse_response.status_code == 401

    # The NEW token, though never misused itself, is now also dead: the
    # whole family was revoked because reuse of an old member was detected.
    client.cookies.set("refresh_token", new_refresh_cookie)
    followup_response = client.post("/api/v1/auth/refresh")
    assert followup_response.status_code == 401


def test_refresh_without_a_cookie_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


def test_logout_revokes_the_session_and_clears_the_cookie(client: TestClient) -> None:
    _register(client)

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


def test_logout_without_a_cookie_is_a_no_op(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204


def test_refresh_without_csrf_header_is_rejected(db_settings: Settings, clean_db: None) -> None:
    with TestClient(create_app(db_settings)) as bare_client:  # no X-Requested-With default
        _register(bare_client)
        response = bare_client.post("/api/v1/auth/refresh")

    assert response.status_code == 403


def test_logout_without_csrf_header_is_rejected(db_settings: Settings, clean_db: None) -> None:
    with TestClient(create_app(db_settings)) as bare_client:  # no X-Requested-With default
        _register(bare_client)
        response = bare_client.post("/api/v1/auth/logout")

    assert response.status_code == 403


def test_register_rejects_password_shorter_than_minimum(client: TestClient) -> None:
    response = _register(client, password="short1")

    assert response.status_code == 422


def test_register_rejects_a_common_password(client: TestClient) -> None:
    response = _register(client, password="password123")

    assert response.status_code == 422


def test_register_ignores_mass_assigned_fields(client: TestClient) -> None:
    response = _register(
        client,
        is_active=False,
        id="11111111-1111-1111-1111-111111111111",
    )

    assert response.status_code == 201
    body = response.json()["user"]
    assert body["is_active"] is True
    assert body["id"] != "11111111-1111-1111-1111-111111111111"


def _deactivate(db_settings: Settings, registration_number: str) -> None:
    engine = create_engine(str(db_settings.database_url))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET is_active = false "
                    "WHERE registration_number = :registration_number"
                ),
                {"registration_number": registration_number},
            )
    finally:
        engine.dispose()


def test_login_rejects_a_deactivated_user(client: TestClient, db_settings: Settings) -> None:
    _register(client)
    _deactivate(db_settings, "DEMO123456")

    response = client.post(
        "/api/v1/auth/login",
        json=LOGIN_PAYLOAD,
    )

    assert response.status_code == 401


def test_me_rejects_a_deactivated_user_even_with_a_still_valid_token(
    client: TestClient, db_settings: Settings
) -> None:
    access_token = _register(client).json()["access_token"]

    _deactivate(db_settings, "DEMO123456")

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 401


def test_editing_the_role_claim_in_a_token_has_no_effect(
    client: TestClient, db_settings: Settings
) -> None:
    """The role in a JWT is never trusted: /me always reflects the DB row."""
    user_id = _register(client).json()["user"]["id"]

    forged_token = create_access_token(uuid.UUID(user_id), "admin", db_settings)

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged_token}"})

    assert response.status_code == 200
    # The registered account is faculty; the forged "admin" claim is ignored.
    assert response.json()["role"] == "faculty"


def test_login_rate_limit_triggers_after_repeated_attempts(client: TestClient) -> None:
    _register(client)

    responses = [
        client.post(
            "/api/v1/auth/login",
            json={**LOGIN_PAYLOAD, "password": "wrong-password"},
        )
        for _ in range(6)
    ]

    assert [r.status_code for r in responses[:4]] == [401, 401, 401, 401]
    assert responses[-1].status_code == 429


def test_change_password_succeeds_and_revokes_every_session(client: TestClient) -> None:
    access_token = _register(client).json()["access_token"]

    response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": "correcthorsebattery", "new_password": "newcorrecthorsebattery"},
    )
    assert response.status_code == 204

    # The refresh token issued at registration is now revoked.
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401

    old_password_login = client.post(
        "/api/v1/auth/login",
        json=LOGIN_PAYLOAD,
    )
    assert old_password_login.status_code == 401

    new_password_login = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "newcorrecthorsebattery"},
    )
    assert new_password_login.status_code == 200


def test_change_password_rejects_wrong_current_password(client: TestClient) -> None:
    access_token = _register(client).json()["access_token"]

    response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": "not-the-password", "new_password": "newcorrecthorsebattery"},
    )

    assert response.status_code == 401


def test_change_password_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "correcthorsebattery", "new_password": "newcorrecthorsebattery"},
    )

    assert response.status_code == 401
