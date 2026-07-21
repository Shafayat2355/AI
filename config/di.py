"""Dependency-injection providers for the configuration system.

Every function here is a plain, synchronous, no-argument callable, which is exactly
what FastAPI's ``Depends()`` (and most other Python DI containers) expect. Handlers
and services should depend on the *narrowest* module they actually need (e.g.
``Depends(get_redis_settings)``) rather than the full ``Settings`` object, per
``docs/CODING_STANDARDS.md`` §8 (Dependency Injection Guidelines) -- this keeps unit
tests for a single component from having to construct the entire configuration tree.

None of these providers are wired into ``app/*_service/main.py`` yet -- that happens
when each service is implemented in a later phase. They are exported now so that work
only has to import and use them.
"""

from __future__ import annotations

from config.factory import SettingsFactory
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
    WebSocketSettings,
)
from config.settings import Settings


def get_settings() -> Settings:
    """DI provider for the full, composed, validated settings tree."""
    return SettingsFactory.create()


def get_application_settings() -> ApplicationSettings:
    """DI provider for :class:`~config.modules.application.ApplicationSettings`."""
    return get_settings().application


def get_database_settings() -> DatabaseSettings:
    """DI provider for :class:`~config.modules.database.DatabaseSettings`."""
    return get_settings().database


def get_postgres_settings() -> PostgreSQLSettings:
    """DI provider for :class:`~config.modules.postgresql.PostgreSQLSettings`."""
    return get_settings().postgres


def get_redis_settings() -> RedisSettings:
    """DI provider for :class:`~config.modules.redis.RedisSettings`."""
    return get_settings().redis


def get_kafka_settings() -> KafkaSettings:
    """DI provider for :class:`~config.modules.kafka.KafkaSettings`."""
    return get_settings().kafka


def get_binance_settings() -> BinanceSettings:
    """DI provider for :class:`~config.modules.binance.BinanceSettings`."""
    return get_settings().binance


def get_ai_model_settings() -> AIModelSettings:
    """DI provider for :class:`~config.modules.ai_models.AIModelSettings`."""
    return get_settings().ai_models


def get_feature_engineering_settings() -> FeatureEngineeringSettings:
    """DI provider for
    :class:`~config.modules.feature_engineering.FeatureEngineeringSettings`."""
    return get_settings().feature_engineering


def get_logging_settings() -> LoggingSettings:
    """DI provider for :class:`~config.modules.logging.LoggingSettings`."""
    return get_settings().logging


def get_monitoring_settings() -> MonitoringSettings:
    """DI provider for :class:`~config.modules.monitoring.MonitoringSettings`."""
    return get_settings().monitoring


def get_api_settings() -> APISettings:
    """DI provider for :class:`~config.modules.api.APISettings`."""
    return get_settings().api


def get_websocket_settings() -> WebSocketSettings:
    """DI provider for :class:`~config.modules.websocket.WebSocketSettings`."""
    return get_settings().websocket


def get_security_settings() -> SecuritySettings:
    """DI provider for :class:`~config.modules.security.SecuritySettings`."""
    return get_settings().security


__all__ = [
    "get_settings",
    "get_application_settings",
    "get_database_settings",
    "get_postgres_settings",
    "get_redis_settings",
    "get_kafka_settings",
    "get_binance_settings",
    "get_ai_model_settings",
    "get_feature_engineering_settings",
    "get_logging_settings",
    "get_monitoring_settings",
    "get_api_settings",
    "get_websocket_settings",
    "get_security_settings",
]
