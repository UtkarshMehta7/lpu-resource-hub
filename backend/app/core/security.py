"""Password hashing, access-token JWTs and opaque refresh tokens.

Refresh tokens are never stored raw: the caller gets the random value once
(to put in a cookie), and only its SHA-256 hash is persisted, so a database
leak does not hand out usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

_password_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"

REFRESH_TOKEN_BYTES = 32

MIN_PASSWORD_LENGTH = 10

# Small, deliberately short blocklist of extremely common passwords. Not a
# substitute for a breach-corpus check (e.g. k-anonymity against HIBP), which
# is out of scope for a local-only prototype; this just rejects the obvious
# ones so `min_length=10` alone can't be satisfied by "password123" etc.
COMMON_PASSWORDS = frozenset(
    {
        "password123",
        "password1234",
        "12345678910",
        "1234567890",
        "qwertyuiop",
        "letmein123",
        "welcome123",
        "iloveyou123",
        "administrator",
        "changeme123",
    }
)


def is_common_password(password: str) -> bool:
    return password.lower() in COMMON_PASSWORDS


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    user_id: uuid.UUID
    role: str
    jti: str


class InvalidAccessTokenError(Exception):
    """Raised when an access token is missing, malformed, expired or tampered with."""


def create_access_token(user_id: uuid.UUID, role: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> AccessTokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError
        return AccessTokenPayload(
            user_id=uuid.UUID(payload["sub"]), role=payload["role"], jti=payload["jti"]
        )
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise InvalidAccessTokenError from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
