"""Unit tests for config.factory.SettingsFactory."""

from __future__ import annotations

import pytest

from config.environment import Environment
from config.factory import SettingsFactory

pytestmark = pytest.mark.usefixtures("isolated_environment")


def _paper_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
    monkeypatch.setenv("BINANCE_API_KEY", "real-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
    monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
    monkeypatch.setenv("POSTGRES_SSLMODE", "require")
    monkeypatch.setenv("MONITORING_TRACING_EXPORTER_ENDPOINT", "http://otel:4317")


class TestSettingsFactory:
    def test_returns_settings_instance(self) -> None:
        settings = SettingsFactory.create("dev")
        assert settings.environment is Environment.DEV

    def test_repeated_calls_return_the_same_cached_instance(self) -> None:
        first = SettingsFactory.create("dev")
        second = SettingsFactory.create("dev")
        assert first is second

    def test_force_reload_returns_a_new_instance(self) -> None:
        first = SettingsFactory.create("dev")
        second = SettingsFactory.create("dev", force_reload=True)
        assert first is not second

    def test_different_environments_are_cached_independently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _paper_ready(monkeypatch)
        dev_settings = SettingsFactory.create("dev")
        paper_settings = SettingsFactory.create("paper")
        assert dev_settings is not paper_settings
        assert dev_settings.environment is Environment.DEV
        assert paper_settings.environment is Environment.PAPER

    def test_clear_cache_specific_environment(self) -> None:
        first = SettingsFactory.create("dev")
        SettingsFactory.clear_cache("dev")
        second = SettingsFactory.create("dev")
        assert first is not second

    def test_clear_cache_all_environments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _paper_ready(monkeypatch)
        SettingsFactory.create("dev")
        SettingsFactory.create("paper")
        SettingsFactory.clear_cache()
        assert SettingsFactory._cache == {}

    def test_create_bootstraps_environment_overlay(self) -> None:
        # dev.yaml sets logging.level: DEBUG; verify the overlay actually reached
        # the constructed Settings via the factory's bootstrap step.
        settings = SettingsFactory.create("dev")
        assert settings.logging.level == "DEBUG"
