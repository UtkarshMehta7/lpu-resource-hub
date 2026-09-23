"""Auth + users integration tests against a real PostgreSQL database.

Requires TEST_DATABASE_URL (skipped otherwise, see conftest.py). Each test
runs against freshly truncated `users`/`refresh_tokens` tables (the `clean_db`
fixture) so tests do not see each other's rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.modules.users.models import UserRole
from tests.conftest import SeededUser

pytestmark = pytest.mark.db

# Nobody self-registers any more (ADR 0019): the account these tests sign in
# with is provisioned for them, exactly as a coordinator would. The password
# is the one tests/conftest.py seeds every account with.
SEEDED_PASSWORD = "not-used-directly-seeded12"
REGISTRATION_NUMBER = "DEMO123456"
LOGIN_PAYLOAD = {"registration_number": REGISTRATION_NUMBER, "password": SEEDED_PASSWORD}


@pytest.fixture
def client(db_settings: Settings, clean_db: None) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        # Real (JS-driven) clients always send this; tests that specifically
        # exercise the CSRF defence build their own client without it.
        test_client.headers["X-Requested-With"] = "XMLHttpRequest"
        yield test_client


@pytest.fixture(autouse=True)
def provisioned_faculty(client: TestClient, seed_user: Callable[..., SeededUser]) -> SeededUser:
    """The account under test, created the way the platform now creates
    accounts: by somebody else.

    Depends on `client` so it is seeded *after* clean_db truncates.
    """
    return seed_user(
        UserRole.FACULTY,
        registration_number=REGISTRATION_NUMBER,
        email="faculty1@example.com",
    )


def _register(client: TestClient, **overrides: object) -> Response:
    """Sign in as the provisioned account.

    Named for what it replaces: every test below used to create its subject
    through POST /auth/register, which no longer exists. The response shape
    is the same (access token + user + refresh cookie), so the assertions
    that follow are unchanged.
    """
    payload = {**LOGIN_PAYLOAD, **overrides}
    return client.post("/api/v1/auth/login", json=payload)


@pytest.mark.parametrize(
    "path", ["/api/v1/auth/register", "/api/v1/auth/signup", "/api/v1/users/register"]
)
def test_there_is_no_public_registration_endpoint(client: TestClient, path: str) -> None:
    """The whole self-service door, closed. Not 403 with a role check behind
    it -- the route does not exist."""
    response = client.post(
        path,
        json={
            "registration_number": "SNEAKY0001",
            "password": "correcthorsebattery",
            "full_name": "Sneaky Person",
            "role": "faculty",
        },
    )

    assert response.status_code == 404


def test_the_openapi_schema_advertises_no_registration(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if "register" in path or "signup" in path]


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
        json={"current_password": SEEDED_PASSWORD, "new_password": "newcorrecthorsebattery"},
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
        json={"current_password": SEEDED_PASSWORD, "new_password": "newcorrecthorsebattery"},
    )

    assert response.status_code == 401
