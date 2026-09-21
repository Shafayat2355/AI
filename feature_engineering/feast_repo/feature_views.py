"""Feast feature view definitions.

Two views -- ``technical_indicators`` and ``statistical_features`` -- both
sourced from the *same* offline parquet file
(``feature_engineering/offline_pipeline.py`` writes one combined file per
batch run; Feast allows several feature views to share one source, selecting
disjoint columns via each view's own ``schema``). Kept as two views rather
than one, matching ``feature_engineering/definitions``'s own module split
(``technical_indicators.py`` vs ``statistical_features.py``), so a caller can
request just one family (``get_online_features([...], ["technical_indicators:sma_20"])``)
without pulling in features it does not need.

Deliberately built by a function (:func:`build_feature_views`), not as
module-level constants -- the offline store path is configuration
(``config.modules.feature_engineering.FeatureEngineeringSettings.offline_store_path``),
and ``feature_engineering/feature_store_client.py`` is the one place that
resolves settings into concrete Feast objects, per this package's
``__init__.py`` docstring.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from feast import FeatureView, Field, FileSource
from feast.types import Float64

from feature_engineering.feast_repo.entities import SYMBOL

#: Every technical-indicator column ``offline_pipeline.py`` computes, per
#: ``feature_engineering/definitions/technical_indicators.py``.
TECHNICAL_INDICATOR_FEATURES: tuple[str, ...] = (
    "sma_20",
    "ema_12",
    "momentum_10",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bollinger_band_width_20",
    "atr_14",
)

#: Every statistical-feature column ``offline_pipeline.py`` computes, per
#: ``feature_engineering/definitions/statistical_features.py``.
STATISTICAL_FEATURES: tuple[str, ...] = (
    "log_return_1",
    "volatility_20",
    "zscore_20",
    "skewness_20",
    "volume_zscore_20",
    "high_low_range_ratio",
)

OFFLINE_FEATURES_FILENAME = "ohlcv_features.parquet"


def build_offline_source(offline_store_path: str) -> FileSource:
    """Build the shared :class:`~feast.FileSource` both feature views read
    from, rooted at ``offline_store_path``
    (``FeatureEngineeringSettings.offline_store_path``)."""
    path = Path(offline_store_path) / OFFLINE_FEATURES_FILENAME
    return FileSource(
        name="ohlcv_features_source",
        path=str(path),
        timestamp_field="event_timestamp",
    )


def build_feature_views(offline_store_path: str) -> tuple[FeatureView, FeatureView]:
    """Build the two feature views, sourced from ``offline_store_path``.

    ``ttl`` bounds how far back Feast will look for a "latest known value"
    when materializing/serving online -- set generously (30 days) since these
    are hourly-bar-derived features, not high-frequency ones.
    """
    source = build_offline_source(offline_store_path)

    technical_indicators = FeatureView(
        name="technical_indicators",
        entities=[SYMBOL],
        ttl=timedelta(days=30),
        schema=[Field(name=col, dtype=Float64) for col in TECHNICAL_INDICATOR_FEATURES],
        online=True,
        source=source,
        description="Technical-indicator features computed by "
        "feature_engineering/definitions/technical_indicators.py.",
    )

    statistical_features = FeatureView(
        name="statistical_features",
        entities=[SYMBOL],
        ttl=timedelta(days=30),
        schema=[Field(name=col, dtype=Float64) for col in STATISTICAL_FEATURES],
        online=True,
        source=source,
        description="Statistical features computed by "
        "feature_engineering/definitions/statistical_features.py.",
    )

    return technical_indicators, statistical_features


def all_feature_refs() -> list[str]:
    """Every ``"<feature_view>:<feature>"`` ref this repo defines -- the
    default ``feature_refs`` ``training/trainer.py`` requests when the caller
    does not narrow to a specific subset."""
    refs = [f"technical_indicators:{c}" for c in TECHNICAL_INDICATOR_FEATURES]
    refs += [f"statistical_features:{c}" for c in STATISTICAL_FEATURES]
    return refs


__all__ = [
    "OFFLINE_FEATURES_FILENAME",
    "STATISTICAL_FEATURES",
    "TECHNICAL_INDICATOR_FEATURES",
    "all_feature_refs",
    "build_feature_views",
    "build_offline_source",
]
