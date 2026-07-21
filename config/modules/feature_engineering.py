"""Feature engineering settings, backing ``feature_engineering/offline_pipeline.py``,
``online_pipeline.py``, and ``feature_store_client.py``.

Environment variables use the ``FEATURE_`` prefix.
"""

from __future__ import annotations

from pydantic import Field

from config.base import ModuleBaseSettings, module_settings_config


class FeatureEngineeringSettings(ModuleBaseSettings):
    """Configuration for the shared offline/online feature computation path."""

    model_config = module_settings_config(env_prefix="FEATURE_")

    online_store_backend: str = Field(
        default="redis", description="Backend for the online (low-latency) feature store."
    )
    online_store_ttl_seconds: int = Field(
        default=3600,
        description="TTL applied to online feature-store entries.",
        ge=1,
    )
    offline_store_path: str = Field(
        default="/var/lib/ai-trading-platform/feature_store/offline",
        description="Filesystem/object-store root for offline (training-time) features.",
    )
    batch_size: int = Field(
        default=1000, description="Row batch size for offline feature computation jobs.", ge=1
    )
    computation_timeout_seconds: float = Field(
        default=60.0, description="Timeout for a single feature-computation invocation.", gt=0
    )
    parallel_workers: int = Field(
        default=4,
        description="Worker processes used by feature_engineering/offline_pipeline.py.",
        ge=1,
    )
    definitions_module: str = Field(
        default="feature_engineering.definitions",
        description="Python module path providing shared feature definitions.",
    )
    enable_online_serving: bool = Field(
        default=True,
        description="Whether feature_store_client.py serves online (low-latency) reads.",
    )


__all__ = ["FeatureEngineeringSettings"]
