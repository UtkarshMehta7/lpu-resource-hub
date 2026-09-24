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
    # Recommendation score weights (Step 9). They should sum to 1.0.
    rec_weight_skill: float = Field(default=0.40, ge=0.0, le=1.0)
    rec_weight_area: float = Field(default=0.35, ge=0.0, le=1.0)
    rec_weight_text: float = Field(default=0.25, ge=0.0, le=1.0)
    # Share of the recommendation *score* given to semantic similarity when
    # embeddings are installed (Step 13). Default 0: the offline evaluation
    # says the hybrid ranks slightly worse than the Step 9 scorer on the
    # labelled set (docs/ai-evaluation.md), so Phase 1 stays the default and
    # this knob exists to re-test as the corpus grows. Semantic *search*
    # (/search/semantic) is unaffected and always on when the extra is
    # installed.
    rec_semantic_weight: float = Field(default=0.0, ge=0.0, le=0.9)
    # Deadline-reminder scheduler (Step 12). Off in tests; on in a real run.
    enable_scheduler: bool = False
    #: Apply outstanding migrations at startup, under an advisory lock.
    #: Defaults to ON in production and off everywhere else -- see
    #: `run_migrations_at_boot` below. Set it explicitly to override.
    run_migrations_on_start: bool | None = None
    reminder_interval_minutes: int = Field(default=60, ge=5, le=1440)

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _normalise_db_scheme(cls, value: object) -> object:
        """Accept the URL every provider actually hands out.

        Neon, Supabase, Heroku and Render all give you `postgres://` or
        `postgresql://`. Which driver SQLAlchemy loads is our implementation
        detail, not something an operator pasting a connection string should
        have to know -- and getting it wrong only surfaced as a crash at
        startup, after a deploy.

        So the driver is added here rather than demanded of the reader.
        Anything that is not PostgreSQL at all is still refused below.
        """
        if not isinstance(value, str):
            return value
        raw = value.strip().strip('"').strip("'")
        for bare in ("postgresql://", "postgres://"):
            if raw.startswith(bare):
                return f"{REQUIRED_DB_SCHEME}://{raw[len(bare) :]}"
        return raw

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _require_psycopg_driver(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        if value is not None and value.scheme != REQUIRED_DB_SCHEME:
            msg = (
                f"must be a PostgreSQL URL; the '{REQUIRED_DB_SCHEME}://' driver is "
                f"added automatically for postgresql:// and postgres://, but got "
                f"'{value.scheme}://'"
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
    def run_migrations_at_boot(self) -> bool:
        """Whether this instance brings its own schema up to date.

        On in production by default, and deliberately not dependent on an
        environment variable being set. render.yaml only governs a service
        synced from the Blueprint; this one was configured by hand, so the
        variable never reached it and the site stayed broken while the code
        that needed the migration was already live (ADR 0024).

        A deployment that cannot migrate itself is a deployment that depends
        on somebody remembering, which is the thing that failed.
        """
        if self.run_migrations_on_start is not None:
            return self.run_migrations_on_start
        return self.is_production

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
