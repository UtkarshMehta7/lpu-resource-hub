"""Password hashing and access-token JWT unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("correcthorsebattery")

    assert hashed != "correcthorsebattery"
    assert verify_password("correcthorsebattery", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correcthorsebattery")

    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip(settings: Settings) -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "student", settings)

    payload = decode_access_token(token, settings)

    assert payload.user_id == user_id
    assert payload.role == "student"


def test_decode_rejects_tampered_token(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), "student", settings)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token + "tampered", settings)


def test_decode_rejects_expired_token(settings: Settings) -> None:
    now = datetime.now(UTC)
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "role": "student",
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, settings)


def test_decode_rejects_token_signed_with_different_key(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), "student", settings)
    other_settings = Settings(
        _env_file=None,
        app_env=settings.app_env,
        database_url=settings.database_url,
        cors_origins=settings.cors_origins,
        jwt_secret_key="a-completely-different-signing-key-of-sufficient-length",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, other_settings)


def test_refresh_token_hash_is_deterministic_and_not_the_raw_value() -> None:
    raw = generate_refresh_token()

    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw


def test_refresh_tokens_are_unique() -> None:
    tokens = {generate_refresh_token() for _ in range(50)}

    assert len(tokens) == 50
