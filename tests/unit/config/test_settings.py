"""Unit tests for config.settings.Settings.

Constructs Settings directly (bypassing SettingsFactory's bootstrap step) with
enough real env vars set that paper/live-only validation rules are satisfied,
so these tests exercise the model itself in isolation from the loader/factory.
"""

from __future__ import annotations

import pytest

from config.environment import Environment
from config.exceptions import ConfigurationValidationError
from config.settings import Settings

pytestmark = pytest.mark.usefixtures("isolated_environment")


def _set_paper_ready_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
    monkeypatch.setenv("BINANCE_API_KEY", "real-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
    monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
    monkeypatch.setenv("POSTGRES_SSLMODE", "require")


class TestSettingsComposition:
    def test_dev_settings_construct_with_no_env_vars(self) -> None:
        settings = Settings(environment=Environment.DEV)
        assert settings.environment.value == "dev"
        assert settings.application.name == "ai-trading-platform"
        assert settings.redis.host == "localhost"

    def test_all_thirteen_modules_present(self) -> None:
        settings = Settings(environment=Environment.DEV)
        for attr in (
            "application",
            "database",
            "postgres",
            "redis",
            "kafka",
            "binance",
            "ai_models",
            "feature_engineering",
            "logging",
            "monitoring",
            "api",
            "websocket",
            "security",
        ):
            assert hasattr(settings, attr)

    def test_debug_flag_propagates_to_application(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG", "true")
        settings = Settings(environment=Environment.DEV)
        assert settings.application.debug is True

    def test_application_debug_propagates_to_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DEBUG", "true")
        settings = Settings(environment=Environment.DEV)
        assert settings.debug is True

    def test_paper_environment_raises_without_secrets(self) -> None:
        with pytest.raises(ConfigurationValidationError):
            Settings(environment=Environment.PAPER)

    def test_paper_environment_succeeds_with_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_paper_ready_env(monkeypatch)
        settings = Settings(environment=Environment.PAPER)
        assert settings.environment.value == "paper"


class TestDatabaseDsn:
    def test_uses_database_url_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
        settings = Settings(environment=Environment.DEV)
        assert settings.database_dsn() == "postgresql+asyncpg://u:p@h:5432/d"

    def test_builds_from_postgres_parts_when_url_unset(self) -> None:
        settings = Settings(environment=Environment.DEV)
        dsn = settings.database_dsn()
        assert dsn.startswith("postgresql+asyncpg://")
        assert "localhost:5432/trading_platform" in dsn


class TestRedisDsn:
    def test_uses_redis_url_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://cache:6380/2")
        settings = Settings(environment=Environment.DEV)
        assert settings.redis_dsn() == "redis://cache:6380/2"

    def test_builds_from_redis_parts_when_url_unset(self) -> None:
        settings = Settings(environment=Environment.DEV)
        assert settings.redis_dsn() == "redis://localhost:6379/0"
