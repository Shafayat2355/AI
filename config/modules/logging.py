"""Logging settings, backing ``shared/logging/logger.py`` and ``correlation.py``.

Environment variables use the ``LOG_`` prefix.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from config.base import ModuleBaseSettings, module_settings_config

_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class LoggingSettings(ModuleBaseSettings):
    """Structured-logging configuration shared by every service."""

    model_config = module_settings_config(env_prefix="LOG_")

    level: str = Field(
        default="INFO", description="Root log level: DEBUG|INFO|WARNING|ERROR|CRITICAL."
    )
    json_format: bool = Field(
        default=True,
        description="Emit structured JSON log lines instead of human-readable text.",
    )
    include_correlation_id: bool = Field(
        default=True,
        description="Attach shared/logging/correlation.py's correlation id to every record.",
    )
    correlation_id_header: str = Field(
        default="X-Correlation-ID",
        description="HTTP header name used to propagate the correlation id.",
    )
    sample_rate: float = Field(
        default=1.0,
        description="Fraction (0-1] of DEBUG/INFO records emitted; 1.0 disables sampling.",
        gt=0.0,
        le=1.0,
    )
    file_path: str | None = Field(
        default=None,
        description="Optional file path for a secondary log sink, in addition to stdout.",
    )
    max_file_size_mb: int = Field(
        default=100, description="Rotation threshold when file_path is set.", ge=1
    )
    backup_count: int = Field(
        default=5, description="Number of rotated log files retained when file_path is set.", ge=0
    )

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _VALID_LEVELS:
            raise ValueError(f"level must be one of {_VALID_LEVELS}, got {value!r}")
        return normalized


__all__ = ["LoggingSettings"]
