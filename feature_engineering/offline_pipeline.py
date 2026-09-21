"""Offline (batch/training-time) feature computation pipeline.

Reads persisted OHLCV history (``datasets/historical/ohlcv_store.py``),
computes every feature in
``feature_engineering/definitions/technical_indicators.py`` and
``statistical_features.py`` per symbol, and writes one combined parquet file
at ``FeatureEngineeringSettings.offline_store_path`` / ``ohlcv_features.parquet``
-- the exact path
``feature_engineering/feast_repo/feature_views.build_offline_source`` points
Feast's ``FileSource`` at. This is what makes "training and inference use the
same feature definitions" (Phase 11 requirement) true in practice: this
module computes the values once, into the file Feast's offline *and* (once
materialized -- ``online_pipeline.py``) online paths both ultimately serve
from.

:func:`run_batch_feature_generation` is the integration point
``scheduler/jobs/feature_generation_job.py`` already calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.domain.entities.tick import OHLCVBar
from datasets.historical.ohlcv_store import INTERVAL_TIMEDELTA, OHLCVStore, SyntheticHistoryConfig
from feature_engineering.definitions import statistical_features as stats
from feature_engineering.definitions import technical_indicators as ti
from feature_engineering.feast_repo.feature_views import (
    OFFLINE_FEATURES_FILENAME,
    STATISTICAL_FEATURES,
    TECHNICAL_INDICATOR_FEATURES,
)
from shared.errors.exceptions import FeatureStoreError
from shared.logging.logger import get_logger

_logger = get_logger("feature_engineering.offline_pipeline")


def bars_to_frame(bars: list[OHLCVBar]) -> pd.DataFrame:
    """Convert a chronologically-ordered list of :class:`OHLCVBar` into the
    ``DataFrame`` shape every function in ``feature_engineering.definitions``
    expects: one row per bar, ``float`` OHLCV columns (Feast/parquet/most
    numeric libraries work in ``float64``, not ``Decimal``), indexed by
    position with ``open_time`` as a column.
    """
    return pd.DataFrame(
        {
            "open_time": [b.open_time for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
        }
    )


def compute_features_for_symbol(symbol: str, bars: list[OHLCVBar]) -> pd.DataFrame:
    """Compute every technical/statistical feature for one symbol's bar
    history. Returns a frame with ``symbol``, ``event_timestamp``, and one
    column per entry in ``TECHNICAL_INDICATOR_FEATURES``/``STATISTICAL_FEATURES``.

    Rows whose rolling windows have not yet warmed up (the first ~26 bars,
    bounded by MACD's slow span) contain ``NaN`` for the affected columns --
    left in place here (not dropped) so the caller decides the policy;
    ``datasets/loaders/training_dataset_loader.py`` drops them before they
    reach a model, per Phase 12's "Missing feature detection" requirement.
    """
    frame = bars_to_frame(bars)
    close = frame["close"]

    features = pd.DataFrame(index=frame.index)
    features["sma_20"] = ti.simple_moving_average(close, 20)
    features["ema_12"] = ti.exponential_moving_average(close, 12)
    features["momentum_10"] = ti.momentum(close, 10)
    features["rsi_14"] = ti.relative_strength_index(close, 14)
    macd_frame = ti.macd(close)
    features["macd"] = macd_frame["macd"]
    features["macd_signal"] = macd_frame["macd_signal"]
    features["macd_histogram"] = macd_frame["macd_histogram"]
    features["bollinger_band_width_20"] = ti.bollinger_band_width(close, 20)
    features["atr_14"] = ti.average_true_range(frame, 14)

    features["log_return_1"] = stats.log_return(close, 1)
    features["volatility_20"] = stats.rolling_volatility(close, 20)
    features["zscore_20"] = stats.rolling_zscore(close, 20)
    features["skewness_20"] = stats.rolling_skewness(close, 20)
    features["volume_zscore_20"] = stats.volume_zscore(frame["volume"], 20)
    features["high_low_range_ratio"] = stats.high_low_range_ratio(frame)

    expected_columns = list(TECHNICAL_INDICATOR_FEATURES) + list(STATISTICAL_FEATURES)
    missing = [c for c in expected_columns if c not in features.columns]
    if missing:  # pragma: no cover - defensive; would indicate a code/schema drift bug
        raise FeatureStoreError(
            "offline feature computation did not produce every expected column",
            context={"missing_columns": missing},
        )

    features.insert(0, "event_timestamp", frame["open_time"])
    features.insert(0, "symbol", symbol)
    return features


@dataclass(frozen=True, slots=True)
class OfflineFeaturePipelineResult:
    symbols_processed: list[str]
    rows_written: int
    output_path: str


class OfflineFeaturePipeline:
    """Orchestrates: read history for each configured symbol -> compute
    features -> write the combined offline parquet file Feast reads."""

    def __init__(self, offline_store_path: str) -> None:
        self._output_dir = Path(offline_store_path)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        history_by_symbol: dict[str, list[OHLCVBar]],
    ) -> OfflineFeaturePipelineResult:
        """Compute features for every symbol in ``history_by_symbol`` and
        write them to one combined parquet file, overwriting any previous
        run's output -- this pipeline always recomputes from the full
        available history rather than appending, which keeps it simple and
        correct at the cost of recomputation cost; acceptable at this
        platform's current data volume (hourly bars, a handful of symbols).
        """
        frames = [
            compute_features_for_symbol(symbol, bars)
            for symbol, bars in history_by_symbol.items()
            if bars
        ]
        if not frames:
            raise FeatureStoreError(
                "no OHLCV history available to compute offline features from",
                context={"symbols_requested": list(history_by_symbol)},
            )
        combined = pd.concat(frames, ignore_index=True)
        output_path = self._output_dir / OFFLINE_FEATURES_FILENAME
        combined.to_parquet(output_path, index=False)
        _logger.info(
            "offline_features_written",
            extra={
                "channel": "application",
                "output_path": str(output_path),
                "rows": len(combined),
                "symbols": list(history_by_symbol),
            },
        )
        return OfflineFeaturePipelineResult(
            symbols_processed=list(history_by_symbol),
            rows_written=len(combined),
            output_path=str(output_path),
        )


async def run_batch_feature_generation(
    *,
    config: SyntheticHistoryConfig | None = None,
) -> dict[str, object]:
    """Integration point called by ``scheduler.jobs.feature_generation_job``.

    Loads persisted OHLCV history for every symbol in ``config.symbols``,
    computes offline features via :class:`OfflineFeaturePipeline`, writes the
    combined parquet file, then (re-)applies this platform's Feast feature
    definitions so the registry stays in sync with
    ``feature_engineering/feast_repo/feature_views.py``. Returns a summary
    dict; raises :class:`~shared.errors.exceptions.FeatureStoreError` on
    failure, which ``call_integration_point`` surfaces as a failed job run.
    """
    from config.settings import get_settings
    from core.container import get_container
    from feature_engineering.feature_store_client import FeastFeatureStoreClient

    settings = get_settings()
    cfg = config or SyntheticHistoryConfig()
    end = datetime.now(UTC)
    start = end - INTERVAL_TIMEDELTA[cfg.interval] * cfg.lookback_bars

    container = get_container()
    history_by_symbol: dict[str, list[OHLCVBar]] = {}
    async for session in container.db.session():
        store = OHLCVStore(session)
        for symbol in cfg.symbols:
            history_by_symbol[symbol] = await store.get_history(
                symbol, cfg.interval, start, end
            )

    pipeline = OfflineFeaturePipeline(settings.feature_engineering.offline_store_path)
    result = pipeline.run(history_by_symbol)

    client = FeastFeatureStoreClient(settings)
    client.apply()

    return {
        "symbols_processed": result.symbols_processed,
        "rows_written": result.rows_written,
        "output_path": result.output_path,
    }


__all__ = [
    "OfflineFeaturePipeline",
    "OfflineFeaturePipelineResult",
    "bars_to_frame",
    "compute_features_for_symbol",
    "run_batch_feature_generation",
]
