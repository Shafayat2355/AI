"""PostgreSQL connection-identity settings: host, credentials, database name.

Environment variables use the ``POSTGRES_`` prefix, e.g. ``POSTGRES_HOST``. These
discrete parts are only used to build a DSN when ``DATABASE_URL``
(:attr:`config.modules.database.DatabaseSettings.url`) is not supplied -- see
:meth:`config.settings.Settings.database_dsn`.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, SecretStr

from config.base import ModuleBaseSettings, module_settings_config


class PostgreSQLSettings(ModuleBaseSettings):
    """Discrete PostgreSQL connection parameters."""

    model_config = module_settings_config(env_prefix="POSTGRES_")

    host: str = Field(default="localhost", description="PostgreSQL server hostname.")
    port: int = Field(default=5432, description="PostgreSQL server port.", ge=1, le=65535)
    user: str = Field(default="trading", description="PostgreSQL login role.")
    password: SecretStr = Field(
        default=SecretStr("trading"),
        description="PostgreSQL login password. Always overridden outside dev.",
    )
    database: str = Field(
        default="trading_platform",
        validation_alias=AliasChoices("POSTGRES_DATABASE", "POSTGRES_DB"),
        description=(
            "Target database name. Also accepts POSTGRES_DB (the official postgres "
            "Docker image's own env var name, used by this repo's docker-compose.yml) "
            "as an alias for POSTGRES_DATABASE, so the local Docker stack and the "
            "application agree on the database name without extra configuration."
        ),
    )
    sslmode: str = Field(
        default="prefer",
        description="libpq sslmode: disable|allow|prefer|require|verify-ca|verify-full.",
    )
    application_name: str = Field(
        default="ai-trading-platform",
        description="Reported to Postgres as application_name for pg_stat_activity visibility.",
    )

    def build_dsn(self, *, driver: str = "postgresql+asyncpg") -> str:
        """Compose a SQLAlchemy DSN from the discrete connection parts.

        Only used as a fallback when no full ``DATABASE_URL`` override is configured.

        Note: ``sslmode`` is only appended as a DSN query parameter for
        ``sslmode``-aware drivers (``psycopg``/``psycopg2``). The ``asyncpg`` dialect
        does not accept ``sslmode`` in the URL -- SSL must instead be passed via
        ``connect_args={"ssl": ...}`` at ``create_async_engine`` call time using
        :attr:`sslmode` to decide whether to build an SSL context.
        """
        user = quote_plus(self.user)
        password = quote_plus(self.password.get_secret_value())
        base = f"{driver}://{user}:{password}@{self.host}:{self.port}/{self.database}"
        if driver.startswith("postgresql+asyncpg"):
            return base
        return f"{base}?sslmode={self.sslmode}"


__all__ = ["PostgreSQLSettings"]
