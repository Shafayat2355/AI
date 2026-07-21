"""Database engine/session settings: connection pooling and SQLAlchemy engine knobs.

Deliberately separate from :mod:`config.modules.postgresql`, which holds the
connection *identity* (host/user/password/db). This module holds how the engine
*behaves* once connected, and optionally a full DSN override.

Environment variables use the ``DATABASE_`` prefix, e.g. ``DATABASE_POOL_SIZE``. The
full-DSN override variable is the unprefixed ``DATABASE_URL``, preserved from the
original ``.env.example`` for backward compatibility with 12-factor-style deployments
that inject one connection string rather than discrete Postgres parts.
"""

from __future__ import annotations

from pydantic import Field, SecretStr

from config.base import ModuleBaseSettings, module_settings_config


class DatabaseSettings(ModuleBaseSettings):
    """SQLAlchemy engine/session configuration shared by every repository
    implementation under ``database/repositories/``."""

    model_config = module_settings_config(env_prefix="DATABASE_")

    url: SecretStr | None = Field(
        default=None,
        description=(
            "Full SQLAlchemy DSN override, e.g. "
            "postgresql+asyncpg://user:pass@host:5432/db. When set, this takes "
            "precedence over config.modules.postgresql.PostgreSQLSettings for DSN "
            "construction (see config.settings.Settings.database_dsn)."
        ),
    )
    driver: str = Field(
        default="postgresql+asyncpg",
        description="SQLAlchemy driver dialect used when composing a DSN from parts.",
    )
    pool_size: int = Field(
        default=10,
        description="Number of persistent connections kept open per process.",
        ge=1,
        le=200,
    )
    max_overflow: int = Field(
        default=20,
        description="Additional connections allowed beyond pool_size under burst load.",
        ge=0,
        le=200,
    )
    pool_timeout_seconds: float = Field(
        default=30.0,
        description="Seconds to wait for a pooled connection before raising.",
        gt=0,
    )
    pool_recycle_seconds: int = Field(
        default=1800,
        description="Recycle connections older than this to dodge stale-connection drops.",
        ge=60,
    )
    connect_timeout_seconds: float = Field(
        default=10.0,
        description="TCP-level connect timeout for a new database connection.",
        gt=0,
    )
    statement_timeout_ms: int = Field(
        default=30_000,
        description="Server-side statement timeout applied to every session.",
        ge=0,
    )
    echo: bool = Field(
        default=False,
        description="Log every emitted SQL statement. Never enabled outside dev.",
    )
    run_migrations_on_startup: bool = Field(
        default=False,
        description="Whether the owning service should run Alembic migrations at boot.",
    )


__all__ = ["DatabaseSettings"]
