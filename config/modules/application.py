"""Application-level settings: service metadata and process-wide toggles.

Environment variables use the ``APP_`` prefix, e.g. ``APP_NAME``, ``APP_DEBUG``.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from config.base import ModuleBaseSettings, module_settings_config


class ApplicationSettings(ModuleBaseSettings):
    """Process-wide application metadata shared by every service entrypoint under
    ``app/*_service/main.py``."""

    model_config = module_settings_config(env_prefix="APP_")

    name: str = Field(
        default="ai-trading-platform",
        description="Human-readable platform name, used in logs and process titles.",
        min_length=1,
    )
    version: str = Field(
        default="0.1.0",
        description="Deployed application version, mirrors pyproject.toml's [project].version.",
        min_length=1,
    )
    description: str = Field(
        default="Institutional-grade, event-driven AI trading platform.",
        description="Short human-readable description surfaced in health-check payloads.",
    )
    debug: bool = Field(
        default=False,
        description=(
            "Enables verbose tracebacks and permissive defaults elsewhere in the "
            "settings tree. Forced to False for paper/live by config.validation."
        ),
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone name all internal timestamps are normalized to.",
    )
    graceful_shutdown_timeout_seconds: float = Field(
        default=30.0,
        description="Seconds a service is given to drain in-flight work on SIGTERM.",
        gt=0,
    )

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}") from exc
        return value


__all__ = ["ApplicationSettings"]
