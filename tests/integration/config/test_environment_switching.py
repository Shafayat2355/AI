"""Integration tests exercising the real ``config/environments/*.yaml`` overlays
shipped in this repository end-to-end through :class:`SettingsFactory`, without
mocking the YAML files or the loader.
"""

from __future__ import annotations

import pytest

from config.environment import Environment
from config.exceptions import ConfigurationValidationError
from config.factory import SettingsFactory

pytestmark = pytest.mark.usefixtures("isolated_environment")


def _paper_and_live_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-production-grade-secret")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-production-db-password")
    monkeypatch.setenv("BINANCE_API_KEY", "real-binance-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "real-binance-secret")
    # Both paper.yaml and live.yaml enable tracing; config.validation requires an
    # explicit collector endpoint whenever tracing is enabled.
    monkeypatch.setenv("MONITORING_TRACING_EXPORTER_ENDPOINT", "http://otel-collector:4317")


class TestDevEnvironmentEndToEnd:
    def test_dev_boots_with_zero_extra_configuration(self) -> None:
        settings = SettingsFactory.create("dev")
        assert settings.environment is Environment.DEV
        assert settings.application.debug is True  # from dev.yaml
        assert settings.logging.level == "DEBUG"  # from dev.yaml
        assert settings.binance.use_testnet is True  # from dev.yaml
        assert settings.api.docs_enabled is True

    def test_dev_kafka_bootstrap_servers_from_overlay(self) -> None:
        settings = SettingsFactory.create("dev")
        assert settings.kafka.bootstrap_servers == ["localhost:9092"]


class TestPaperEnvironmentEndToEnd:
    def test_paper_rejects_boot_without_secrets(self) -> None:
        with pytest.raises(ConfigurationValidationError):
            SettingsFactory.create("paper")

    def test_paper_boots_with_secrets_supplied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _paper_and_live_secrets(monkeypatch)
        settings = SettingsFactory.create("paper")
        assert settings.environment is Environment.PAPER
        assert settings.application.debug is False
        assert settings.security.secure_cookies is True  # from paper.yaml
        assert settings.kafka.security_protocol == "SASL_SSL"  # from paper.yaml
        assert settings.binance.use_testnet is True  # paper still trades against testnet
        assert settings.monitoring.tracing_enabled is True


class TestLiveEnvironmentEndToEnd:
    def test_live_rejects_boot_without_secrets(self) -> None:
        with pytest.raises(ConfigurationValidationError):
            SettingsFactory.create("live")

    def test_live_boots_with_secrets_supplied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _paper_and_live_secrets(monkeypatch)
        settings = SettingsFactory.create("live")
        assert settings.environment is Environment.LIVE
        assert settings.api.docs_enabled is False  # from live.yaml
        assert settings.binance.use_testnet is False  # from live.yaml
        assert settings.postgres.sslmode == "verify-full"  # from live.yaml
        assert settings.security.min_password_length == 14  # from live.yaml

    def test_live_and_paper_are_independently_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _paper_and_live_secrets(monkeypatch)
        paper_settings = SettingsFactory.create("paper")
        live_settings = SettingsFactory.create("live")
        assert paper_settings.binance.use_testnet is True
        assert live_settings.binance.use_testnet is False


class TestEnvironmentVariableDrivesDefaultResolution:
    def test_environment_variable_selects_environment_when_unspecified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "dev")
        settings = SettingsFactory.create()
        assert settings.environment is Environment.DEV
