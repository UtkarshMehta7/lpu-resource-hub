"""Typed application settings loaded from environment variables and `.env`."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REQUIRED_DB_SCHEME = "postgresql+psycopg"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application configuration.

    Required values have no default so that a missing variable stops startup
    with a clear validation error naming it.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LPU Research Intelligence & Collaboration Hub"
    app_env: Environment
    database_url: PostgresDsn
    test_database_url: PostgresDsn | None = None
    cors_origins: Annotated[list[str], NoDecode]
    log_level: LogLevel = "INFO"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_connect_timeout: int = Field(default=5, ge=1, le=60)
    jwt_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _require_psycopg_driver(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        if value is not None and value.scheme != REQUIRED_DB_SCHEME:
            msg = (
                f"must use the '{REQUIRED_DB_SCHEME}://' scheme "
                f"(psycopg 3 driver), got '{value.scheme}://'"
            )
            raise ValueError(msg)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors_origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one origin is required")
        for origin in value:
            if origin != "*" and not origin.startswith(("http://", "https://")):
                raise ValueError(f"origin '{origin}' must start with http:// or https://")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env is not Environment.PRODUCTION:
            return self
        for origin in self.cors_origins:
            if origin == "*":
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
            if (urlsplit(origin).hostname or "") in LOCAL_HOSTS:
                raise ValueError(
                    f"CORS_ORIGINS must not contain local origin '{origin}' in production"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are disabled in production."""
        return not self.is_production

    @property
    def refresh_token_expire_seconds(self) -> int:
        return self.refresh_token_expire_days * 24 * 60 * 60

    def database_summary(self) -> str:
        """Human-readable database target for logs. Never includes the password."""
        host = self.database_url.hosts()[0]
        database = (self.database_url.path or "/").lstrip("/")
        return (
            f"database={database!r} host={host.get('host')}:{host.get('port')} "
            f"user={host.get('username')!r}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once."""
    return Settings()
