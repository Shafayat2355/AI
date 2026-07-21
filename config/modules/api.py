"""API-layer settings, backing ``app/api_service/main.py`` and ``api/routers/*``.

Environment variables use the ``API_`` prefix.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import NoDecode

from config.base import ModuleBaseSettings, module_settings_config


class APISettings(ModuleBaseSettings):
    """External-facing HTTP API configuration."""

    model_config = module_settings_config(env_prefix="API_")

    host: str = Field(default="0.0.0.0", description="Bind address for the API service.")  # noqa: S104
    port: int = Field(default=8000, description="Bind port for the API service.", ge=1, le=65535)
    root_path: str = Field(
        default="", description="ASGI root_path when served behind a proxy prefix."
    )
    prefix: str = Field(default="/api/v1", description="Path prefix applied to every router.")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins. Never '*' outside dev -- enforced by config.validation.",
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow credentialed CORS requests."
    )
    request_timeout_seconds: float = Field(
        default=30.0, description="Per-request server-side timeout.", gt=0
    )
    rate_limit_requests_per_minute: int = Field(
        default=120, description="Per-client rate limit enforced by api/middleware.", ge=1
    )
    max_request_body_bytes: int = Field(
        default=2_097_152, description="Maximum accepted request body size, in bytes.", ge=1
    )
    docs_enabled: bool = Field(
        default=True, description="Expose /docs and /openapi.json. Disabled in live by default."
    )
    workers: int = Field(default=1, description="Number of ASGI worker processes.", ge=1)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("prefix")
    @classmethod
    def _validate_prefix(cls, value: str) -> str:
        if value and not value.startswith("/"):
            raise ValueError(f"prefix must start with '/', got {value!r}")
        return value.rstrip("/")


__all__ = ["APISettings"]
