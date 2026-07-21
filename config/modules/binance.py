"""Binance settings, backing ``market_data/feed_adapters/`` and ``live_trading/broker_gateway.py``.

Environment variables use the ``BINANCE_`` prefix. ``api_key``/``api_secret`` also
accept the original ``.env.example`` variable ``MARKET_DATA_VENDOR_API_KEY`` as a
fallback alias for the key, so existing local ``.env`` files created before this phase
keep working without edits.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr

from config.base import ModuleBaseSettings, module_settings_config


class BinanceSettings(ModuleBaseSettings):
    """Binance REST/WebSocket API configuration."""

    model_config = module_settings_config(env_prefix="BINANCE_")

    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("BINANCE_API_KEY", "MARKET_DATA_VENDOR_API_KEY"),
        description="Binance API key. Required outside dev.",
    )
    api_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("BINANCE_API_SECRET", "MARKET_DATA_VENDOR_API_SECRET"),
        description="Binance API secret. Required outside dev.",
    )
    rest_base_url: str = Field(
        default="https://api.binance.com",
        description="Binance REST API base URL.",
    )
    websocket_base_url: str = Field(
        default="wss://stream.binance.com:9443",
        description="Binance market-data WebSocket base URL.",
    )
    use_testnet: bool = Field(
        default=True,
        description="Route to Binance's testnet endpoints instead of production.",
    )
    recv_window_ms: int = Field(
        default=5000,
        description="Binance recvWindow parameter for signed REST requests.",
        ge=100,
        le=60_000,
    )
    request_timeout_seconds: float = Field(
        default=10.0, description="HTTP client timeout for REST calls.", gt=0
    )
    max_requests_per_minute: int = Field(
        default=1200,
        description="Client-side rate-limit ceiling, kept under Binance's published weight limits.",
        ge=1,
    )
    reconnect_backoff_seconds: float = Field(
        default=2.0,
        description="Initial backoff before a WebSocket reconnect attempt.",
        gt=0,
    )
    reconnect_backoff_max_seconds: float = Field(
        default=60.0,
        description="Ceiling for exponential WebSocket reconnect backoff.",
        gt=0,
    )

    @property
    def effective_rest_base_url(self) -> str:
        """The REST base URL, adjusted for testnet when :attr:`use_testnet` is set."""
        if self.use_testnet and self.rest_base_url == "https://api.binance.com":
            return "https://testnet.binance.vision"
        return self.rest_base_url

    @property
    def effective_websocket_base_url(self) -> str:
        """The WebSocket base URL, adjusted for testnet when :attr:`use_testnet` is set."""
        if self.use_testnet and self.websocket_base_url == "wss://stream.binance.com:9443":
            return "wss://testnet.binance.vision"
        return self.websocket_base_url


__all__ = ["BinanceSettings"]
