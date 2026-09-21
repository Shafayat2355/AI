"""Assembles labeled training datasets from historical data and features.

Bridges ``core.ports.feature_store_port.FeatureStorePort`` (point-in-time
historical feature retrieval) and label construction: given an
entity/timestamp frame, retrieve historical features via Feast, attach a
binary "did the next bar close up" label computed from the same OHLCV
history, and validate the result against
``datasets/schemas/dataset_schema.TrainingDatasetSchema`` before handing it to
``training/trainer.py``.

This is the one place label leakage would most easily creep in (a label
computed from a bar the corresponding feature row could not have seen yet),
so :func:`build_labels` is deliberately simple rather than folded into a
larger function.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.domain.entities.tick import OHLCVBar
from core.ports.feature_store_port import FeatureStorePort
from datasets.schemas.dataset_schema import TrainingDatasetSchema
from feature_engineering.feast_repo.feature_views import (
    STATISTICAL_FEATURES,
    TECHNICAL_INDICATOR_FEATURES,
    all_feature_refs,
)
from shared.errors.exceptions import FeatureValidationError


def build_labels(bars: list[OHLCVBar], *, horizon: int = 1) -> pd.DataFrame:
    """Build the binary "next bar closes up" label for each bar in ``bars``
    (chronologically ordered, single symbol).

    Row ``i``'s label describes bar ``i + horizon`` relative to bar ``i`` --
    it is *about the future relative to that row's own timestamp*, which is
    exactly what an entity_df's ``event_timestamp`` must stay aligned with
    for Feast's point-in-time join to remain leakage-free: the label for the
    row timestamped at bar ``i`` is knowable only once bar ``i + horizon``
    closes, never before. The last ``horizon`` rows have no future bar to
    label and are dropped.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    if len(bars) <= horizon:
        return pd.DataFrame(columns=["symbol", "event_timestamp", "label"])

    symbol = bars[0].symbol
    rows = []
    for i in range(len(bars) - horizon):
        current = bars[i]
        future = bars[i + horizon]
        rows.append(
            {
                "symbol": symbol,
                # Features calculated from ``current`` are available only
                # once its OHLCV candle closes, never at its open time.
                "event_timestamp": current.close_time,
                "label": int(future.close > current.close),
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True, slots=True)
class TrainingDataset:
    """A fully assembled, validated training dataset: feature rows joined to
    labels, ready for ``training.trainer.ModelTrainer.split``."""

    frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    feature_refs: tuple[str, ...]


class TrainingDatasetLoader:
    """Builds a :class:`TrainingDataset` for one symbol from a
    :class:`~core.ports.feature_store_port.FeatureStorePort` plus OHLCV
    history already fetched by the caller (``training/trainer.py``, which
    owns the database session those bars came from)."""

    def __init__(self, feature_store: FeatureStorePort) -> None:
        self._feature_store = feature_store

    def build(
        self,
        symbol: str,
        bars: list[OHLCVBar],
        *,
        label_horizon: int = 1,
        feature_refs: list[str] | None = None,
    ) -> TrainingDataset:
        refs = feature_refs or all_feature_refs()
        labels = build_labels(bars, horizon=label_horizon)
        if labels.empty:
            raise FeatureValidationError(
                f"not enough OHLCV history for {symbol} to build any labeled rows",
                context={"bars_available": len(bars), "label_horizon": label_horizon},
            )

        entity_df = labels[["symbol", "event_timestamp"]].copy()
        historical = self._feature_store.get_historical_features(entity_df, refs)

        merged = historical.merge(labels, on=["symbol", "event_timestamp"], how="inner")
        merged = merged.dropna(
            subset=[c for c in TECHNICAL_INDICATOR_FEATURES + STATISTICAL_FEATURES if c in merged]
        )
        if merged.empty:
            raise FeatureValidationError(
                f"no rows remained for {symbol} after joining features to labels and "
                f"dropping unwarmed rolling-window rows",
                context={"symbol": symbol},
            )

        feature_columns = tuple(
            c for c in TECHNICAL_INDICATOR_FEATURES + STATISTICAL_FEATURES if c in merged.columns
        )
        schema = TrainingDatasetSchema(
            feature_columns=feature_columns, numeric_feature_columns=feature_columns
        )
        schema.validate(merged)

        return TrainingDataset(
            frame=merged.reset_index(drop=True),
            feature_columns=feature_columns,
            feature_refs=tuple(refs),
        )


__all__ = ["TrainingDataset", "TrainingDatasetLoader", "build_labels"]
