"""AI model settings, backing ``models/registry_client.py``, ``inference/``, and
``mlops/`` (registry lookup, canary routing, drift thresholds).

Environment variables use the ``AI_MODEL_`` prefix.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from config.base import ModuleBaseSettings, module_settings_config


class AIModelSettings(ModuleBaseSettings):
    """Model registry, inference, and canary-routing configuration."""

    model_config = module_settings_config(env_prefix="AI_MODEL_")

    registry_uri: str = Field(
        default="file:///var/lib/ai-trading-platform/model_registry",
        description="URI of the model registry (mlflow:// or file:// backed).",
    )
    default_model_name: str = Field(
        default="baseline-momentum",
        description="Model name loaded when a strategy does not pin a specific model.",
    )
    default_model_stage: str = Field(
        default="champion",
        description="Registry stage resolved by default: champion|challenger|archived.",
    )
    inference_timeout_ms: int = Field(
        default=250,
        description="Hard timeout for a single inference call, enforced by inference/predictor.py.",
        ge=1,
    )
    max_batch_size: int = Field(
        default=64, description="Maximum batch size accepted by the inference service.", ge=1
    )
    device: str = Field(
        default="cpu", description="Inference device: cpu|cuda|cuda:N."
    )
    model_cache_dir: str = Field(
        default="/var/cache/ai-trading-platform/models",
        description="Local filesystem cache for downloaded model artifacts.",
    )
    canary_traffic_percentage: float = Field(
        default=0.0,
        description="Percentage (0-100) of inference traffic routed to the challenger model.",
        ge=0.0,
        le=100.0,
    )
    drift_check_interval_seconds: int = Field(
        default=300,
        description="Interval between drift-detector evaluations in mlops/drift_detector.py.",
        ge=1,
    )
    drift_score_threshold: float = Field(
        default=0.25,
        description="Drift score above which mlops/drift_detector.py raises an alert.",
        ge=0.0,
    )
    auto_rollback_on_drift: bool = Field(
        default=True,
        description="Whether to auto-rollback to the previous champion on drift breach (live).",
    )

    @field_validator("device")
    @classmethod
    def _validate_device(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "cpu" and not normalized.startswith("cuda"):
            raise ValueError(f"device must be 'cpu' or start with 'cuda', got {value!r}")
        return normalized


__all__ = ["AIModelSettings"]
