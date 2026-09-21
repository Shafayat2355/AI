"""Schema definitions/validation for dataset tables used in training and backtesting.

Two things live here:

* :class:`TrainingDatasetSchema` -- the expected column set/dtypes of a
  training dataset produced by
  ``datasets/loaders/training_dataset_loader.py`` from Feast historical
  features, and the feature/type/missing-value validation
  ``feature_engineering/offline_pipeline.py`` and ``training/trainer.py`` both
  run against a dataset before using it (Phase 11/12's "Feature validation" /
  "Feature schema validation" / "Missing feature detection" / "Type
  validation" requirements).
* :func:`validate_latest_data` -- the integration point
  ``scheduler/jobs/data_validation_job.py`` already calls, checking the most
  recently persisted OHLCV history for gaps/nulls before a training run relies
  on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from shared.errors.exceptions import FeatureValidationError
from shared.logging.logger import get_logger

_logger = get_logger("datasets.schemas.dataset_schema")

#: Columns every training dataset must carry regardless of which features were
#: requested -- the entity key, the point-in-time join column, and the label.
REQUIRED_BASE_COLUMNS: tuple[str, ...] = ("symbol", "event_timestamp", "label")


@dataclass(frozen=True, slots=True)
class TrainingDatasetSchema:
    """Expected shape of a training dataset: base columns plus a named,
    typed set of feature columns.

    ``feature_columns`` is deliberately explicit (not "whatever columns
    happen to be in the DataFrame") so a silently dropped or renamed feature
    -- e.g. a Feast feature view rename -- is caught as a schema mismatch
    instead of training on fewer features than intended.
    """

    feature_columns: tuple[str, ...]
    numeric_feature_columns: tuple[str, ...] = field(default=())

    def all_columns(self) -> tuple[str, ...]:
        return REQUIRED_BASE_COLUMNS + self.feature_columns

    def validate(self, df: pd.DataFrame) -> None:
        """Validate ``df`` against this schema in full: missing columns,
        missing (null) feature values, and feature dtypes.

        Raises :class:`~shared.errors.exceptions.FeatureValidationError` on
        the first category of violation found (missing columns first, since a
        type/null check on a column that does not exist is meaningless).
        Never silently coerces or drops rows -- a caller that wants that
        behavior does so explicitly after inspecting the raised error's
        ``context``.
        """
        missing_columns = [c for c in self.all_columns() if c not in df.columns]
        if missing_columns:
            raise FeatureValidationError(
                "training dataset is missing required columns",
                context={"missing_columns": missing_columns},
            )

        null_counts = {
            col: int(df[col].isna().sum())
            for col in self.feature_columns
            if df[col].isna().any()
        }
        if null_counts:
            raise FeatureValidationError(
                "training dataset contains missing (null) feature values",
                context={"null_counts": null_counts},
            )

        type_mismatches: dict[str, str] = {}
        for col in self.numeric_feature_columns:
            if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
                type_mismatches[col] = str(df[col].dtype)
        if type_mismatches:
            raise FeatureValidationError(
                "training dataset feature columns failed type validation",
                context={"non_numeric_columns": type_mismatches},
            )


def detect_missing_features(df: pd.DataFrame, expected_features: list[str]) -> list[str]:
    """Return which of ``expected_features`` are absent from ``df``'s columns.

    Standalone helper (in addition to :meth:`TrainingDatasetSchema.validate`)
    for callers -- e.g. ``inference/predictor.py`` validating an online
    feature payload -- that want the list without a raised exception."""
    return [f for f in expected_features if f not in df.columns]


def check_training_serving_consistency(
    training_features: list[str], serving_features: list[str]
) -> list[str]:
    """Return any feature present in ``training_features`` but absent from
    ``serving_features`` -- a skew that would silently degrade a model at
    inference time (Phase 11's "Training/serving consistency checks" /
    Phase 12's "training/serving feature consistency" requirement).

    Deliberately one-directional: ``serving_features`` may legitimately expose
    extra features a particular model version does not use.
    """
    serving_set = set(serving_features)
    return [f for f in training_features if f not in serving_set]


async def validate_latest_data(*, symbol: str | None = None) -> dict[str, object]:
    """Integration point called by ``scheduler.jobs.data_validation_job``.

    Checks the most recently persisted OHLCV history (via
    ``datasets.historical.ohlcv_store.OHLCVStore``) for the data-quality
    issues a downstream feature/training pipeline cares about: time-ordering
    gaps larger than one interval, and negative volumes. Returns a summary
    dict; raises :class:`~shared.errors.exceptions.FeatureValidationError` if
    any symbol fails validation, which ``call_integration_point`` surfaces as
    a failed job run.
    """
    from datasets.historical.ohlcv_store import (
        INTERVAL_TIMEDELTA,
        OHLCVStore,
        SyntheticHistoryConfig,
    )

    cfg = SyntheticHistoryConfig()
    symbols = [symbol] if symbol else list(cfg.symbols)
    end = datetime.now(UTC)
    start = end - INTERVAL_TIMEDELTA[cfg.interval] * cfg.lookback_bars * 2
    report: dict[str, object] = {}
    failures: dict[str, list[str]] = {}

    from core.container import get_container

    container = get_container()
    async for session in container.db.session():
        store = OHLCVStore(session)
        for sym in symbols:
            bars = await store.get_history(sym, cfg.interval, start, end)
            issues: list[str] = []
            if not bars:
                issues.append("no bars persisted yet")
            else:
                expected_gap = INTERVAL_TIMEDELTA[cfg.interval]
                for prev, curr in zip(bars, bars[1:], strict=False):
                    if curr.open_time - prev.open_time > expected_gap:
                        issues.append(f"gap between {prev.open_time} and {curr.open_time}")
                for bar in bars:
                    if bar.volume < 0:
                        issues.append(f"negative volume at {bar.open_time}")
            report[sym] = {"bar_count": len(bars), "issues": issues}
            if issues:
                failures[sym] = issues

    if failures:
        _logger.warning(
            "dataset_validation_failed",
            extra={"channel": "application", "failures": failures},
        )
        raise FeatureValidationError(
            "latest OHLCV data failed validation", context={"failures": failures}
        )

    _logger.info("dataset_validation_passed", extra={"channel": "application", "report": report})
    return report


__all__ = [
    "REQUIRED_BASE_COLUMNS",
    "TrainingDatasetSchema",
    "check_training_serving_consistency",
    "detect_missing_features",
    "validate_latest_data",
]
