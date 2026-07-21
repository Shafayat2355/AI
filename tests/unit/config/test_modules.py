"""Unit tests for each standalone settings module in config/modules/.

Each module is tested for: sane defaults, environment-variable overrides using its
own prefix, and field-level validation failures. Tests use ``isolated_environment``
so setting env vars in one test never leaks into another.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.modules.ai_models import AIModelSettings
from config.modules.api import APISettings
from config.modules.application import ApplicationSettings
from config.modules.binance import BinanceSettings
from config.modules.database import DatabaseSettings
from config.modules.feature_engineering import FeatureEngineeringSettings
from config.modules.kafka import KafkaSettings
from config.modules.logging import LoggingSettings
from config.modules.monitoring import MonitoringSettings
from config.modules.postgresql import PostgreSQLSettings
from config.modules.redis import RedisSettings
from config.modules.security import INSECURE_DEFAULT_SECRET, SecuritySettings
from config.modules.websocket import WebSocketSettings

pytestmark = pytest.mark.usefixtures("isolated_environment")


class TestApplicationSettings:
    def test_defaults(self) -> None:
        settings = ApplicationSettings()
        assert settings.name == "ai-trading-platform"
        assert settings.debug is False
        assert settings.timezone == "UTC"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_NAME", "custom-name")
        monkeypatch.setenv("APP_DEBUG", "true")
        settings = ApplicationSettings()
        assert settings.name == "custom-name"
        assert settings.debug is True

    def test_invalid_timezone_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_TIMEZONE", "Not/AZone")
        with pytest.raises(ValidationError, match="Unknown IANA timezone"):
            ApplicationSettings()

    def test_negative_shutdown_timeout_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", "-1")
        with pytest.raises(ValidationError):
            ApplicationSettings()


class TestDatabaseSettings:
    def test_defaults(self) -> None:
        settings = DatabaseSettings()
        assert settings.url is None
        assert settings.pool_size == 10
        assert settings.driver == "postgresql+asyncpg"

    def test_database_url_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
        settings = DatabaseSettings()
        assert settings.url is not None
        assert settings.url.get_secret_value() == "postgresql+asyncpg://u:p@h:5432/d"

    def test_pool_size_out_of_range_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_POOL_SIZE", "0")
        with pytest.raises(ValidationError):
            DatabaseSettings()


class TestPostgreSQLSettings:
    def test_defaults(self) -> None:
        settings = PostgreSQLSettings()
        assert settings.host == "localhost"
        assert settings.port == 5432

    def test_build_dsn_asyncpg_omits_sslmode(self) -> None:
        settings = PostgreSQLSettings(host="db", user="u", password="p", database="d")  # type: ignore[call-arg]
        dsn = settings.build_dsn(driver="postgresql+asyncpg")
        assert dsn == "postgresql+asyncpg://u:p@db:5432/d"
        assert "sslmode" not in dsn

    def test_build_dsn_psycopg_includes_sslmode(self) -> None:
        settings = PostgreSQLSettings(  # type: ignore[call-arg]
            host="db", user="u", password="p", database="d", sslmode="require"
        )
        dsn = settings.build_dsn(driver="postgresql+psycopg2")
        assert dsn == "postgresql+psycopg2://u:p@db:5432/d?sslmode=require"

    def test_build_dsn_url_encodes_special_characters(self) -> None:
        settings = PostgreSQLSettings(  # type: ignore[call-arg]
            host="db", user="u@ser", password="p@ss/word", database="d"
        )
        dsn = settings.build_dsn(driver="postgresql+asyncpg")
        assert "u%40ser" in dsn
        assert "p%40ss%2Fword" in dsn

    def test_invalid_port_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_PORT", "70000")
        with pytest.raises(ValidationError):
            PostgreSQLSettings()


class TestRedisSettings:
    def test_defaults(self) -> None:
        settings = RedisSettings()
        assert settings.host == "localhost"
        assert settings.build_dsn() == "redis://localhost:6379/0"

    def test_build_dsn_with_password_and_tls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_PASSWORD", "secret")
        monkeypatch.setenv("REDIS_USE_TLS", "true")
        settings = RedisSettings()
        assert settings.build_dsn() == "rediss://:secret@localhost:6379/0"

    def test_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://cache:6380/2")
        settings = RedisSettings()
        assert settings.url is not None
        assert settings.url.get_secret_value() == "redis://cache:6380/2"

    def test_db_out_of_range_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_DB", "16")
        with pytest.raises(ValidationError):
            RedisSettings()


class TestKafkaSettings:
    def test_defaults(self) -> None:
        settings = KafkaSettings()
        assert settings.bootstrap_servers == ["localhost:9092"]
        assert settings.security_protocol == "PLAINTEXT"

    def test_bootstrap_servers_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "a:9092, b:9092 ,c:9092")
        settings = KafkaSettings()
        assert settings.bootstrap_servers == ["a:9092", "b:9092", "c:9092"]

    def test_empty_bootstrap_servers_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "")
        with pytest.raises(ValidationError, match="at least one host:port"):
            KafkaSettings()

    def test_security_protocol_normalized_and_validated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "sasl_ssl")
        settings = KafkaSettings()
        assert settings.security_protocol == "SASL_SSL"

    def test_invalid_security_protocol_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "NOT_A_PROTOCOL")
        with pytest.raises(ValidationError, match="security_protocol must be one of"):
            KafkaSettings()


class TestBinanceSettings:
    def test_defaults(self) -> None:
        settings = BinanceSettings()
        assert settings.api_key is None
        assert settings.use_testnet is True

    def test_binance_prefixed_key_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BINANCE_API_KEY", "k1")
        settings = BinanceSettings()
        assert settings.api_key is not None
        assert settings.api_key.get_secret_value() == "k1"

    def test_legacy_market_data_vendor_key_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MARKET_DATA_VENDOR_API_KEY", "legacy-key")
        settings = BinanceSettings()
        assert settings.api_key is not None
        assert settings.api_key.get_secret_value() == "legacy-key"

    def test_effective_rest_base_url_switches_for_testnet(self) -> None:
        settings = BinanceSettings(use_testnet=True)  # type: ignore[call-arg]
        assert settings.effective_rest_base_url == "https://testnet.binance.vision"

    def test_effective_rest_base_url_respects_explicit_override(self) -> None:
        settings = BinanceSettings(use_testnet=True, rest_base_url="https://custom.example")  # type: ignore[call-arg]
        assert settings.effective_rest_base_url == "https://custom.example"


class TestAIModelSettings:
    def test_defaults(self) -> None:
        settings = AIModelSettings()
        assert settings.device == "cpu"
        assert settings.canary_traffic_percentage == 0.0

    def test_device_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_MODEL_DEVICE", "CUDA:0")
        settings = AIModelSettings()
        assert settings.device == "cuda:0"

    def test_invalid_device_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_MODEL_DEVICE", "tpu")
        with pytest.raises(ValidationError, match="device must be"):
            AIModelSettings()

    def test_canary_percentage_out_of_range_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AI_MODEL_CANARY_TRAFFIC_PERCENTAGE", "101")
        with pytest.raises(ValidationError):
            AIModelSettings()


class TestFeatureEngineeringSettings:
    def test_defaults(self) -> None:
        settings = FeatureEngineeringSettings()
        assert settings.online_store_backend == "redis"
        assert settings.enable_online_serving is True

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FEATURE_BATCH_SIZE", "5000")
        settings = FeatureEngineeringSettings()
        assert settings.batch_size == 5000


class TestLoggingSettings:
    def test_defaults(self) -> None:
        settings = LoggingSettings()
        assert settings.level == "INFO"
        assert settings.json_format is True

    def test_level_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        settings = LoggingSettings()
        assert settings.level == "DEBUG"

    def test_invalid_level_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError, match="level must be one of"):
            LoggingSettings()

    def test_sample_rate_out_of_range_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_SAMPLE_RATE", "1.5")
        with pytest.raises(ValidationError):
            LoggingSettings()


class TestMonitoringSettings:
    def test_defaults(self) -> None:
        settings = MonitoringSettings()
        assert settings.metrics_enabled is True
        assert settings.tracing_enabled is False

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MONITORING_METRICS_PORT", "9200")
        settings = MonitoringSettings()
        assert settings.metrics_port == 9200


class TestAPISettings:
    def test_defaults(self) -> None:
        settings = APISettings()
        assert settings.port == 8000
        assert settings.cors_allowed_origins == ["http://localhost:3000"]

    def test_cors_origins_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_CORS_ALLOWED_ORIGINS", "https://a.example,https://b.example")
        settings = APISettings()
        assert settings.cors_allowed_origins == ["https://a.example", "https://b.example"]

    def test_prefix_must_start_with_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_PREFIX", "api/v1")
        with pytest.raises(ValidationError, match="prefix must start with"):
            APISettings()

    def test_prefix_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_PREFIX", "/api/v1/")
        settings = APISettings()
        assert settings.prefix == "/api/v1"


class TestWebSocketSettings:
    def test_defaults(self) -> None:
        settings = WebSocketSettings()
        assert settings.port == 8001
        assert settings.path == "/ws"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBSOCKET_MAX_CONNECTIONS", "500")
        settings = WebSocketSettings()
        assert settings.max_connections == 500


class TestSecuritySettings:
    def test_defaults_use_insecure_placeholder(self) -> None:
        settings = SecuritySettings()
        assert settings.jwt_secret.get_secret_value() == INSECURE_DEFAULT_SECRET

    def test_security_prefixed_secret_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_JWT_SECRET", "real-secret")
        settings = SecuritySettings()
        assert settings.jwt_secret.get_secret_value() == "real-secret"

    def test_legacy_jwt_secret_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_SECRET", "legacy-real-secret")
        settings = SecuritySettings()
        assert settings.jwt_secret.get_secret_value() == "legacy-real-secret"

    def test_allowed_hosts_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_ALLOWED_HOSTS", "a.example, b.example")
        settings = SecuritySettings()
        assert settings.allowed_hosts == ["a.example", "b.example"]

    def test_jwt_algorithm_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_JWT_ALGORITHM", "hs256")
        settings = SecuritySettings()
        assert settings.jwt_algorithm == "HS256"

    def test_invalid_jwt_algorithm_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_JWT_ALGORITHM", "none")
        with pytest.raises(ValidationError, match="jwt_algorithm must be one of"):
            SecuritySettings()

    def test_min_password_length_floor_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_MIN_PASSWORD_LENGTH", "4")
        with pytest.raises(ValidationError):
            SecuritySettings()
