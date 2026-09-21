"""Unit tests for dataset schema validation and labeled-dataset assembly:
``datasets/schemas/dataset_schema.py`` and
``datasets/loaders/training_dataset_loader.py``.

The loader is exercised against a small in-test
:class:`~core.ports.feature_store_port.FeatureStorePort` implementation rather
than a mock object -- a real (if trivial) port implementation keeps these
tests honest about the interface's actual contract, and the Feast-backed
implementation is covered separately by the integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from core.domain.entities.tick import BarInterval, OHLCVBar
from core.ports.feature_store_port import FeatureStorePort
from datasets.loaders.training_dataset_loader import TrainingDatasetLoader, build_labels
from datasets.schemas.dataset_schema import (
    TrainingDatasetSchema,
    check_training_serving_consistency,
    detect_missing_features,
)
from shared.errors.exceptions import FeatureValidationError

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(index: int, close: float) -> OHLCVBar:
    value = Decimal(str(close))
    return OHLCVBar(
        symbol="BTCUSDT",
        interval=BarInterval.ONE_HOUR,
        open_time=_ANCHOR + timedelta(hours=index),
        open=value,
        high=value,
        low=value,
        close=value,
        volume=Decimal("100"),
    )


class _StubFeatureStore(FeatureStorePort):
    """Minimal in-memory FeatureStorePort returning one constant feature per
    requested ref, joined onto whatever entity rows it is given."""

    def __init__(self, *, feature_values: dict[str, float] | None = None) -> None:
        self.feature_values = feature_values or {"sma_20": 1.0, "rsi_14": 50.0}
        self.historical_calls: list[pd.DataFrame] = []

    def get_historical_features(
        self, entity_df: pd.DataFrame, feature_refs: list[str] | None = None
    ) -> pd.DataFrame:
        self.historical_calls.append(entity_df.copy())
        result = entity_df.copy()
        for name, value in self.feature_values.items():
            result[name] = value
        return result

    def get_online_features(
        self, entity_rows: list[dict[str, Any]], feature_refs: list[str] | None = None
    ) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {"symbol": [r["symbol"] for r in entity_rows]}
        for name, value in self.feature_values.items():
            out[name] = [value] * len(entity_rows)
        return out

    def materialize(self, start_date: datetime, end_date: datetime) -> None:
        return None

    def apply(self) -> None:
        return None


class TestBuildLabels:
    def test_labels_one_as_up_when_the_future_bar_closes_higher(self) -> None:
        labels = build_labels([_bar(0, 100), _bar(1, 101)], horizon=1)
        assert labels["label"].tolist() == [1]

    def test_labels_zero_when_the_future_bar_closes_lower_or_flat(self) -> None:
        assert build_labels([_bar(0, 100), _bar(1, 99)], horizon=1)["label"].tolist() == [0]
        assert build_labels([_bar(0, 100), _bar(1, 100)], horizon=1)["label"].tolist() == [0]

    def test_each_rows_timestamp_is_its_own_bar_never_the_future_bar(self) -> None:
        """The anti-leakage invariant: a row's event_timestamp must be the
        timestamp of the bar the features are known at, not the labelled one."""
        bars = [_bar(i, 100 + i) for i in range(5)]
        labels = build_labels(bars, horizon=1)
        assert labels["event_timestamp"].tolist() == [b.close_time for b in bars[:-1]]

    def test_drops_the_trailing_rows_that_have_no_future_bar(self) -> None:
        bars = [_bar(i, 100 + i) for i in range(10)]
        assert len(build_labels(bars, horizon=3)) == 7

    def test_returns_empty_when_history_is_shorter_than_the_horizon(self) -> None:
        assert build_labels([_bar(0, 100)], horizon=5).empty

    def test_rejects_a_non_positive_horizon(self) -> None:
        with pytest.raises(ValueError, match="horizon"):
            build_labels([_bar(0, 100)], horizon=0)

    def test_a_longer_horizon_compares_against_the_correct_future_bar(self) -> None:
        # close values 100, 1, 2, 300 -> horizon 3 compares bar0 (100) to bar3 (300)
        bars = [_bar(0, 100), _bar(1, 1), _bar(2, 2), _bar(3, 300)]
        assert build_labels(bars, horizon=3)["label"].tolist() == [1]


class TestTrainingDatasetSchema:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "symbol": ["BTCUSDT"],
                "event_timestamp": [_ANCHOR],
                "label": [1],
                "sma_20": [1.5],
            }
        )

    def test_accepts_a_well_formed_frame(self) -> None:
        TrainingDatasetSchema(
            feature_columns=("sma_20",), numeric_feature_columns=("sma_20",)
        ).validate(self._frame())

    def test_rejects_a_frame_missing_a_declared_feature_column(self) -> None:
        with pytest.raises(FeatureValidationError, match="missing required columns"):
            TrainingDatasetSchema(feature_columns=("sma_20", "absent")).validate(self._frame())

    def test_rejects_a_frame_missing_the_label_column(self) -> None:
        frame = self._frame().drop(columns=["label"])
        with pytest.raises(FeatureValidationError, match="missing required columns"):
            TrainingDatasetSchema(feature_columns=("sma_20",)).validate(frame)

    def test_rejects_null_feature_values(self) -> None:
        frame = self._frame()
        frame.loc[0, "sma_20"] = None
        with pytest.raises(FeatureValidationError, match="null"):
            TrainingDatasetSchema(feature_columns=("sma_20",)).validate(frame)

    def test_rejects_a_non_numeric_feature_column(self) -> None:
        frame = self._frame()
        frame["sma_20"] = ["not a number"]
        with pytest.raises(FeatureValidationError, match="type validation"):
            TrainingDatasetSchema(
                feature_columns=("sma_20",), numeric_feature_columns=("sma_20",)
            ).validate(frame)

    def test_reports_which_columns_were_missing_in_the_error_context(self) -> None:
        with pytest.raises(FeatureValidationError) as excinfo:
            TrainingDatasetSchema(feature_columns=("a", "b")).validate(self._frame())
        assert set(excinfo.value.context["missing_columns"]) == {"a", "b"}


class TestConsistencyHelpers:
    def test_detect_missing_features_lists_only_absent_ones(self) -> None:
        frame = pd.DataFrame({"a": [1]})
        assert detect_missing_features(frame, ["a", "b"]) == ["b"]

    def test_training_serving_consistency_flags_features_absent_at_serving(self) -> None:
        assert check_training_serving_consistency(["a", "b"], ["a"]) == ["b"]

    def test_extra_serving_features_are_not_a_skew(self) -> None:
        assert check_training_serving_consistency(["a"], ["a", "b"]) == []


class TestTrainingDatasetLoader:
    def test_builds_a_validated_dataset_joining_features_to_labels(self) -> None:
        store = _StubFeatureStore()
        bars = [_bar(i, 100 + i) for i in range(10)]
        dataset = TrainingDatasetLoader(store).build(
            "BTCUSDT", bars, feature_refs=["technical_indicators:sma_20"]
        )
        assert "label" in dataset.frame.columns
        assert len(dataset.frame) == 9  # 10 bars - 1 unlabelable trailing bar
        assert dataset.feature_refs == ("technical_indicators:sma_20",)

    def test_passes_only_entity_and_timestamp_columns_to_the_feature_store(self) -> None:
        """The label must never be sent to the feature store -- doing so would
        make leakage possible in a store that echoed inputs back."""
        store = _StubFeatureStore()
        TrainingDatasetLoader(store).build("BTCUSDT", [_bar(i, 100 + i) for i in range(5)])
        assert list(store.historical_calls[0].columns) == ["symbol", "event_timestamp"]

    def test_drops_rows_whose_features_are_null(self) -> None:
        store = _StubFeatureStore(feature_values={"sma_20": float("nan")})
        with pytest.raises(FeatureValidationError, match="no rows remained"):
            TrainingDatasetLoader(store).build(
                "BTCUSDT", [_bar(i, 100 + i) for i in range(10)]
            )

    def test_raises_when_history_is_too_short_to_label(self) -> None:
        with pytest.raises(FeatureValidationError, match="not enough OHLCV history"):
            TrainingDatasetLoader(_StubFeatureStore()).build("BTCUSDT", [_bar(0, 100)])
