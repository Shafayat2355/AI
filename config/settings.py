"""Typed settings loader (env vars + environment YAML) used by every service at boot.

``Settings`` is the composition root for the entire configuration tree: one field per
domain module (see ``config/modules/``), plus the resolved deployment
:class:`~config.environment.Environment` and the top-level ``debug`` flag.

Services should not construct ``Settings()`` directly -- use :func:`get_settings`
(or, for DI, ``config.di.get_settings``) so the environment-overlay bootstrap and
cross-module validation in :mod:`config.factory` always run first.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from config.base import module_settings_config
from config.environment import Environment, resolve_environment
from config.modules import (
    AIModelSettings,
    APISettings,
    ApplicationSettings,
    BinanceSettings,
    DatabaseSettings,
    FeatureEngineeringSettings,
    KafkaSettings,
    LoggingSettings,
    MonitoringSettings,
    PostgreSQLSettings,
    RedisSettings,
    SecuritySettings,
    TrainingSettings,
    WebSocketSettings,
)


class Settings(BaseSettings):
    """Fully-typed, validated configuration for one running process.

    Every field below is independently readable from the environment (each nested
    module owns its own prefix, see ``config/modules/``); ``environment`` and
    ``debug`` are the only genuinely root-level, unprefixed variables
    (``ENVIRONMENT``, ``DEBUG``), matching the original ``.env.example``.
    """

    model_config = module_settings_config(env_prefix="")

    environment: Environment = Field(
        default_factory=resolve_environment,
        description="Active deployment environment: dev|paper|live.",
    )
    debug: bool = Field(
        default=False,
        description="Root debug toggle. When unset, mirrors application.debug for convenience.",
    )

    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    postgres: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    binance: BinanceSettings = Field(default_factory=BinanceSettings)
    ai_models: AIModelSettings = Field(default_factory=AIModelSettings)
    feature_engineering: FeatureEngineeringSettings = Field(
        default_factory=FeatureEngineeringSettings
    )
    training: TrainingSettings = Field(default_factory=TrainingSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    api: APISettings = Field(default_factory=APISettings)
    websocket: WebSocketSettings = Field(default_factory=WebSocketSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @model_validator(mode="after")
    def _sync_debug_flags(self) -> Settings:
        """Keep the root ``debug`` flag and ``application.debug`` in agreement.

        Operators only need to set one of ``DEBUG`` or ``APP_DEBUG``; if only one is
        set, the other is brought into agreement rather than left to silently diverge.
        """
        if self.debug and not self.application.debug:
            self.application.debug = True
        elif self.application.debug and not self.debug:
            self.debug = True
        return self

    def database_dsn(self) -> str:
        """Resolve the effective SQLAlchemy DSN: ``database.url`` if set, else built
        from the discrete ``postgres`` parts using ``database.driver``."""
        if self.database.url is not None:
            return self.database.url.get_secret_value()
        return self.postgres.build_dsn(driver=self.database.driver)

    def redis_dsn(self) -> str:
        """Resolve the effective Redis DSN: ``redis.url`` if set, else built from the
        discrete ``redis`` connection parts."""
        if self.redis.url is not None:
            return self.redis.url.get_secret_value()
        return self.redis.build_dsn()

    def model_post_init(self, __context: object) -> None:
        """Fail fast on cross-module rules that a single field validator cannot see."""
        from config.validation import validate_settings

        validate_settings(self)


def get_settings(
    environment: Environment | str | None = None, *, force_reload: bool = False
) -> Settings:
    """Return the process-wide :class:`Settings` singleton for ``environment``.

    Thin, import-friendly wrapper around :class:`config.factory.SettingsFactory` --
    kept here because ``config/settings.py`` is the module every existing
    ``docs/CODING_STANDARDS.md`` reference (§13) already points services at.
    """
    from config.factory import SettingsFactory

    return SettingsFactory.create(environment, force_reload=force_reload)


__all__ = ["Settings", "get_settings"]
