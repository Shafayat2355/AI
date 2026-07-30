"""Redis settings, backing ``cache/redis_client.py`` and the online feature store.

Environment variables use the ``REDIS_`` prefix, plus the unprefixed ``REDIS_URL``
override preserved from the original ``.env.example`` (field name ``url`` + prefix
``REDIS_`` resolves to exactly ``REDIS_URL`` by pydantic-settings' default rule).
"""

from __future__ import annotations

from pydantic import Field, SecretStr

from config.base import ModuleBaseSettings, module_settings_config


class RedisSettings(ModuleBaseSettings):
    """Redis connection and pooling configuration."""

    model_config = module_settings_config(env_prefix="REDIS_")

    url: SecretStr | None = Field(
        default=None,
        description=(
            "Full Redis URL override, e.g. redis://user:pass@host:6379/0. Takes "
            "precedence over the discrete host/port/db fields when set."
        ),
    )
    host: str = Field(default="localhost", description="Redis server hostname.")
    port: int = Field(default=6379, description="Redis server port.", ge=1, le=65535)
    db: int = Field(default=0, description="Redis logical database index.", ge=0, le=15)
    password: SecretStr | None = Field(default=None, description="Redis AUTH password, if any.")
    use_tls: bool = Field(default=False, description="Connect using rediss:// (TLS) instead of redis://.")
    max_connections: int = Field(
        default=50, description="Maximum size of the shared Redis connection pool.", ge=1
    )
    socket_timeout_seconds: float = Field(
        default=5.0, description="Per-command socket timeout.", gt=0
    )
    socket_connect_timeout_seconds: float = Field(
        default=5.0, description="TCP connect timeout for new Redis connections.", gt=0
    )
    health_check_interval_seconds: int = Field(
        default=30, description="Interval between idle-connection liveness checks.", ge=0
    )
    decode_responses: bool = Field(
        default=True, description="Decode Redis byte responses to str automatically."
    )
    key_prefix: str = Field(
        default="trading:",
        description="Prefix applied to every cache key, see cache/cache_keys.py.",
    )
    connect_retry_attempts: int = Field(
        default=5,
        description=(
            "Attempts RedisConnection.connect_with_retry makes before giving up. "
            "Not used by check_connection (which never retries) or by any code path "
            "run automatically at startup -- see cache.redis_client.RedisConnection."
        ),
        ge=1,
        le=20,
    )
    connect_retry_backoff_seconds: float = Field(
        default=1.0,
        description="Base backoff between connect_with_retry attempts (doubles each retry).",
        gt=0,
    )
    prediction_cache_ttl_seconds: int = Field(
        default=300,
        description="Default TTL for cache.prediction_cache.PredictionCache entries.",
        ge=1,
    )
    market_cache_ttl_seconds: int = Field(
        default=5,
        description=(
            "Default TTL for cache.market_cache.MarketCache entries -- short, since "
            "market data goes stale within seconds."
        ),
        ge=1,
    )
    session_cache_ttl_seconds: int = Field(
        default=1800,
        description="Default TTL for cache.session_cache.SessionCache entries (30 minutes).",
        ge=1,
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        description="Default fixed-window size for cache.rate_limit_cache.RateLimitCache.",
        ge=1,
    )

    def build_dsn(self) -> str:
        """Compose a ``redis(s)://`` DSN from the discrete connection parts.

        Only used as a fallback when :attr:`url` is not configured.
        """
        scheme = "rediss" if self.use_tls else "redis"
        auth = f":{self.password.get_secret_value()}@" if self.password else ""
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


__all__ = ["RedisSettings"]
