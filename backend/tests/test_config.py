"""Settings validation: required values, driver scheme, CORS and production rules."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

DB_URL = "postgresql+psycopg://user:secret@localhost:5432/example"
ENV_VARS = ("APP_ENV", "DATABASE_URL", "TEST_DATABASE_URL", "CORS_ORIGINS", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def build(**values: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "development",
        "database_url": DB_URL,
        "cors_origins": "http://localhost:5173",
    }
    base.update(values)
    return Settings(_env_file=None, **base)


def test_loads_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173/")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings(_env_file=None)

    assert settings.app_env is Environment.DEVELOPMENT
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.log_level == "DEBUG"
    assert settings.docs_enabled is True


@pytest.mark.parametrize("missing", ["app_env", "database_url", "cors_origins"])
def test_required_values_fail_clearly_when_missing(missing: str) -> None:
    values: dict[str, Any] = {
        "app_env": "development",
        "database_url": DB_URL,
        "cors_origins": "http://localhost:5173",
    }
    del values[missing]

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **values)

    assert missing in str(excinfo.value)


def test_rejects_non_psycopg_driver() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        build(database_url="postgresql://user:secret@localhost:5432/example")


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
