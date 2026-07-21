"""Monitoring settings, backing ``monitoring/health_checks.py`` and ``metrics_exporter.py``.

Environment variables use the ``MONITORING_`` prefix.
"""

from __future__ import annotations

from pydantic import Field

from config.base import ModuleBaseSettings, module_settings_config


class MonitoringSettings(ModuleBaseSettings):
    """Metrics, tracing, and health-check configuration."""

    model_config = module_settings_config(env_prefix="MONITORING_")

    metrics_enabled: bool = Field(
        default=True, description="Expose a Prometheus metrics endpoint."
    )
    metrics_port: int = Field(
        default=9100, description="Port the metrics endpoint binds to.", ge=1, le=65535
    )
    metrics_path: str = Field(
        default="/metrics", description="HTTP path serving Prometheus metrics."
    )
    tracing_enabled: bool = Field(default=False, description="Emit distributed traces.")
    tracing_exporter_endpoint: str | None = Field(
        default=None, description="OTLP collector endpoint, required when tracing_enabled=True."
    )
    tracing_sample_rate: float = Field(
        default=0.1, description="Fraction (0-1] of requests traced.", gt=0.0, le=1.0
    )
    health_check_interval_seconds: int = Field(
        default=15, description="Interval between internal liveness/readiness self-checks.", ge=1
    )
    health_check_timeout_seconds: float = Field(
        default=5.0, description="Timeout for a single dependency health check.", gt=0
    )
    alert_on_health_check_failures: int = Field(
        default=3,
        description="Consecutive failed health checks before alerts/alert_manager.py fires.",
        ge=1,
    )


__all__ = ["MonitoringSettings"]
