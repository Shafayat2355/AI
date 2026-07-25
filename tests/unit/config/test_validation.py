"""Unit tests for config.validation.validate_settings.

Exercises each rule individually via direct Settings() construction (which calls
validate_settings from model_post_init), asserting both the failure and the
corresponding fix.
"""

from __future__ import annotations

import pytest

from config.environment import Environment
from config.exceptions import ConfigurationValidationError
from config.settings import Settings

pytestmark = pytest.mark.usefixtures("isolated_environment")


def _minimal_paper_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
    monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
    monkeypatch.setenv("BINANCE_API_KEY", "real-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
    monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
    monkeypatch.setenv("POSTGRES_SSLMODE", "require")


class TestDevIsExemptFromProductionRules:
    def test_dev_allows_debug_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DEBUG", "true")
        Settings(environment=Environment.DEV)  # must not raise

    def test_dev_allows_placeholder_secret(self) -> None:
        Settings(environment=Environment.DEV)  # must not raise despite default jwt_secret


class TestDebugModeRule:
    def test_paper_rejects_debug_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("APP_DEBUG", "true")
        with pytest.raises(ConfigurationValidationError, match="debug must be False"):
            Settings(environment=Environment.PAPER)


class TestSecretPlaceholderRule:
    def test_paper_rejects_placeholder_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
        monkeypatch.setenv("BINANCE_API_KEY", "real-key")
        monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
        monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
        monkeypatch.setenv("POSTGRES_SSLMODE", "require")
        with pytest.raises(ConfigurationValidationError, match="jwt_secret is still"):
            Settings(environment=Environment.PAPER)

    def test_paper_rejects_placeholder_postgres_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
        monkeypatch.setenv("BINANCE_API_KEY", "real-key")
        monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
        monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
        monkeypatch.setenv("POSTGRES_SSLMODE", "require")
        with pytest.raises(ConfigurationValidationError, match="postgres.password"):
            Settings(environment=Environment.PAPER)

    def test_database_url_override_exempts_postgres_password_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
        monkeypatch.setenv("BINANCE_API_KEY", "real-key")
        monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
        monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
        monkeypatch.setenv("POSTGRES_SSLMODE", "require")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:realpass@h:5432/d")
        Settings(environment=Environment.PAPER)  # must not raise


class TestCorsWildcardRule:
    def test_paper_rejects_wildcard_cors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("API_CORS_ALLOWED_ORIGINS", "*")
        with pytest.raises(ConfigurationValidationError, match="cors_allowed_origins"):
            Settings(environment=Environment.PAPER)


class TestDocsDisabledInLiveRule:
    def test_live_rejects_docs_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("BINANCE_USE_TESTNET", "false")
        monkeypatch.setenv("API_DOCS_ENABLED", "true")
        with pytest.raises(ConfigurationValidationError, match="docs_enabled must be False"):
            Settings(environment=Environment.LIVE)

    def test_paper_allows_docs_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("API_DOCS_ENABLED", "true")
        Settings(environment=Environment.PAPER)  # must not raise


class TestBinanceCredentialsRule:
    def test_paper_rejects_missing_binance_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
        monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
        monkeypatch.setenv("SECURITY_SECURE_COOKIES", "true")
        monkeypatch.setenv("POSTGRES_SSLMODE", "require")
        with pytest.raises(ConfigurationValidationError, match="binance.api_key"):
            Settings(environment=Environment.PAPER)

    def test_live_rejects_testnet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("API_DOCS_ENABLED", "false")
        with pytest.raises(ConfigurationValidationError, match="use_testnet must be False"):
            Settings(environment=Environment.LIVE)


class TestTlsEnforcementRule:
    def test_paper_rejects_insecure_cookies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_JWT_SECRET", "a-real-secret-value")
        monkeypatch.setenv("POSTGRES_PASSWORD", "a-real-db-password")
        monkeypatch.setenv("BINANCE_API_KEY", "real-key")
        monkeypatch.setenv("BINANCE_API_SECRET", "real-secret")
        monkeypatch.setenv("POSTGRES_SSLMODE", "require")
        with pytest.raises(ConfigurationValidationError, match="secure_cookies must be True"):
            Settings(environment=Environment.PAPER)

    def test_paper_rejects_permissive_sslmode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _minimal_paper_secrets(monkeypatch)
        monkeypatch.setenv("POSTGRES_SSLMODE", "disable")
        with pytest.raises(ConfigurationValidationError, match="too permissive"):
            Settings(environment=Environment.PAPER)


class TestTracingEndpointRule:
    def test_tracing_enabled_without_endpoint_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONITORING_TRACING_ENABLED", "true")
        with pytest.raises(ConfigurationValidationError, match="tracing_exporter_endpoint"):
            Settings(environment=Environment.DEV)

    def test_tracing_enabled_with_endpoint_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONITORING_TRACING_ENABLED", "true")
        monkeypatch.setenv("MONITORING_TRACING_EXPORTER_ENDPOINT", "http://otel:4317")
        Settings(environment=Environment.DEV)  # must not raise


class TestAllErrorsReportedTogether:
    def test_multiple_violations_all_appear_in_one_message(self) -> None:
        with pytest.raises(ConfigurationValidationError) as excinfo:
            Settings(environment=Environment.PAPER)
        message = str(excinfo.value)
        assert "jwt_secret" in message
        assert "postgres.password" in message
        assert "binance.api_key" in message
