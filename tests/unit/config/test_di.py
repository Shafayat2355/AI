"""Unit tests for config.di dependency-injection providers."""

from __future__ import annotations

import pytest

from config import di
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

pytestmark = pytest.mark.usefixtures("isolated_environment")


class TestDIProviders:
    def test_get_settings_returns_settings(self) -> None:
        assert isinstance(di.get_settings(), Settings)

    @pytest.mark.parametrize(
        ("provider", "expected_type"),
        [
            (di.get_application_settings, ApplicationSettings),
            (di.get_database_settings, DatabaseSettings),
            (di.get_postgres_settings, PostgreSQLSettings),
            (di.get_redis_settings, RedisSettings),
            (di.get_kafka_settings, KafkaSettings),
            (di.get_binance_settings, BinanceSettings),
            (di.get_ai_model_settings, AIModelSettings),
            (di.get_feature_engineering_settings, FeatureEngineeringSettings),
            (di.get_logging_settings, LoggingSettings),
            (di.get_monitoring_settings, MonitoringSettings),
            (di.get_api_settings, APISettings),
            (di.get_websocket_settings, WebSocketSettings),
            (di.get_security_settings, SecuritySettings),
        ],
    )
    def test_each_provider_returns_the_correct_module_type(
        self, provider: object, expected_type: type
    ) -> None:
        result = provider()  # type: ignore[operator]
        assert isinstance(result, expected_type)

    def test_module_provider_reflects_full_settings_tree(self) -> None:
        settings = di.get_settings()
        assert di.get_redis_settings() == settings.redis
