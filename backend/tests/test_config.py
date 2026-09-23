"""Settings validation: required values, driver scheme, CORS and production rules."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

DB_URL = "postgresql+psycopg://user:secret@localhost:5432/example"
JWT_SECRET = "unit-test-jwt-signing-key-at-least-32-characters-long"
ENV_VARS = (
    "APP_ENV",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "CORS_ORIGINS",
    "LOG_LEVEL",
    "JWT_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def build(**values: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "development",
        "database_url": DB_URL,
        "cors_origins": "http://localhost:5173",
        "jwt_secret_key": JWT_SECRET,
    }
    base.update(values)
    return Settings(_env_file=None, **base)


def test_loads_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173/")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)

    settings = Settings(_env_file=None)

    assert settings.app_env is Environment.DEVELOPMENT
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.log_level == "DEBUG"
    assert settings.docs_enabled is True


@pytest.mark.parametrize("missing", ["app_env", "database_url", "cors_origins", "jwt_secret_key"])
def test_required_values_fail_clearly_when_missing(missing: str) -> None:
    values: dict[str, Any] = {
        "app_env": "development",
        "database_url": DB_URL,
        "cors_origins": "http://localhost:5173",
        "jwt_secret_key": JWT_SECRET,
    }
    del values[missing]

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **values)

    assert missing in str(excinfo.value)


def test_upgrades_a_bare_postgresql_url_rather_than_refusing_it() -> None:
    """This used to raise. Demanding the driver prefix of whoever pastes a
    connection string bought nothing and cost a failed deploy."""
    settings = build(database_url="postgresql://user:secret@localhost:5432/example")

    assert str(settings.database_url).startswith("postgresql+psycopg://")


def test_rejects_short_jwt_secret_key() -> None:
    with pytest.raises(ValidationError):
        build(jwt_secret_key="too-short")


def test_rejects_malformed_cors_origin() -> None:
    with pytest.raises(ValidationError, match="must start with http"):
        build(cors_origins="localhost:5173")


@pytest.mark.parametrize(
    "origins", ["*", "http://localhost:5173", "https://app.example.org,http://127.0.0.1:3000"]
)
def test_production_rejects_wildcard_and_local_origins(origins: str) -> None:
    with pytest.raises(ValidationError):
        build(app_env="production", cors_origins=origins)


def test_production_accepts_explicit_origin_and_disables_docs() -> None:
    settings = build(app_env="production", cors_origins="https://research-hub.example.org")

    assert settings.is_production is True
    assert settings.docs_enabled is False


def test_database_summary_never_contains_password() -> None:
    summary = build().database_summary()

    assert "secret" not in summary
    assert "example" in summary
    assert "localhost:5432" in summary


# ---------------------------------------------- the connection string people paste


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u:p@host/db",  # what Neon and Supabase show
        "postgres://u:p@host/db",  # what Heroku-style URLs look like
        "postgresql+psycopg://u:p@host/db",  # already correct
        '  "postgresql://u:p@host/db"  ',  # pasted with quotes and spaces
    ],
)
def test_every_shape_of_postgres_url_is_accepted(raw: str) -> None:
    """Which driver SQLAlchemy loads is our implementation detail. An operator
    pasting a provider's connection string should not have to know it, and
    getting it wrong used to mean a crash at startup after a deploy."""
    settings = Settings(
        app_env="development",
        database_url=raw,
        cors_origins="http://localhost:5173",
        jwt_secret_key="x" * 40,
    )

    assert str(settings.database_url).startswith("postgresql+psycopg://")


def test_something_that_is_not_postgres_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="development",
            database_url="mysql://u:p@host/db",
            cors_origins="http://localhost:5173",
            jwt_secret_key="x" * 40,
        )
