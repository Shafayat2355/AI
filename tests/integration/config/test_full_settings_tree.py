"""Integration tests for the fully-composed settings tree and its DI wiring."""

from __future__ import annotations

import pytest

from config import di
from config.factory import SettingsFactory
from config.settings import Settings

pytestmark = pytest.mark.usefixtures("isolated_environment")


class TestFullSettingsTree:
    def test_settings_tree_is_fully_typed_and_populated(self) -> None:
        settings = SettingsFactory.create("dev")
        assert isinstance(settings, Settings)

        assert isinstance(settings.database.pool_size, int)
        assert isinstance(settings.redis.port, int)
        assert isinstance(settings.kafka.bootstrap_servers, list)
        assert all(isinstance(item, str) for item in settings.kafka.bootstrap_servers)
        assert isinstance(settings.api.cors_allowed_origins, list)
        assert isinstance(settings.security.jwt_secret.get_secret_value(), str)
        assert isinstance(settings.ai_models.canary_traffic_percentage, float)

    def test_dsn_helpers_are_usable_end_to_end(self) -> None:
        settings = SettingsFactory.create("dev")
        assert settings.database_dsn().startswith("postgresql+asyncpg://")
        assert settings.redis_dsn().startswith("redis://")


class TestDIWiringMatchesFactory:
    def test_di_get_settings_matches_factory_singleton(self) -> None:
        via_factory = SettingsFactory.create("dev")
        via_di = di.get_settings()
        assert via_factory is via_di

    def test_di_module_providers_all_resolve_from_same_tree(self) -> None:
        settings = di.get_settings()
        assert di.get_application_settings() is settings.application
        assert di.get_database_settings() is settings.database
        assert di.get_postgres_settings() is settings.postgres
        assert di.get_redis_settings() is settings.redis
        assert di.get_kafka_settings() is settings.kafka
        assert di.get_binance_settings() is settings.binance
        assert di.get_ai_model_settings() is settings.ai_models
        assert di.get_feature_engineering_settings() is settings.feature_engineering
        assert di.get_logging_settings() is settings.logging
        assert di.get_monitoring_settings() is settings.monitoring
        assert di.get_api_settings() is settings.api
        assert di.get_websocket_settings() is settings.websocket
        assert di.get_security_settings() is settings.security
