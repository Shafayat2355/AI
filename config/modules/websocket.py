"""WebSocket settings, backing ``websocket/server.py``, ``connection_manager.py``,
and ``session_store.py``.

Environment variables use the ``WEBSOCKET_`` prefix.
"""

from __future__ import annotations

from pydantic import Field

from config.base import ModuleBaseSettings, module_settings_config


class WebSocketSettings(ModuleBaseSettings):
    """Real-time WebSocket gateway configuration."""

    model_config = module_settings_config(env_prefix="WEBSOCKET_")

    host: str = Field(default="0.0.0.0", description="Bind address for the WebSocket service.")  # noqa: S104
    port: int = Field(
        default=8001, description="Bind port for the WebSocket service.", ge=1, le=65535
    )
    path: str = Field(default="/ws", description="URL path the WebSocket endpoint is served on.")
    max_connections: int = Field(
        default=10_000, description="Maximum concurrent connections per process.", ge=1
    )
    heartbeat_interval_seconds: float = Field(
        default=15.0, description="Server-initiated ping interval.", gt=0
    )
    ping_timeout_seconds: float = Field(
        default=10.0,
        description="Time to wait for a pong before considering a connection dead.",
        gt=0,
    )
    max_message_size_bytes: int = Field(
        default=65_536, description="Maximum accepted inbound message size.", ge=1
    )
    send_queue_max_size: int = Field(
        default=1000,
        description="Per-connection outbound queue depth before backpressure is applied.",
        ge=1,
    )
    session_ttl_seconds: int = Field(
        default=3600, description="TTL for session_store.py session records.", ge=1
    )


__all__ = ["WebSocketSettings"]
