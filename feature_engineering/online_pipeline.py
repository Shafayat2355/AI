"""Online (materialization) feature pipeline.

Thin wrapper around ``core.ports.feature_store_port.FeatureStorePort.materialize``
-- pushes feature values already computed by ``offline_pipeline.py`` into the
Feast online store (Redis, per ``feature_engineering/feast_repo/repo_builder.py``),
so ``inference/predictor.py`` can serve them with low latency via
``get_online_features`` instead of paying an offline-store read on every
prediction request.

Kept as its own module (rather than folded into ``offline_pipeline.py``)
because it has a different natural cadence: offline feature computation runs
whenever new OHLCV history lands, while materialization is what needs to run
*more frequently* (e.g. every few minutes) to keep the online store fresh for
live inference, even between offline recomputation runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.ports.feature_store_port import FeatureStorePort
from shared.errors.exceptions import FeatureStoreError
from shared.logging.logger import get_logger

_logger = get_logger("feature_engineering.online_pipeline")


@dataclass(frozen=True, slots=True)
class OnlinePipelineResult:
    start_date: datetime
    end_date: datetime


class OnlineFeaturePipeline:
    """Materializes a window of already-computed offline feature values into
    the online store, through the injected :class:`FeatureStorePort`."""

    def __init__(self, feature_store: FeatureStorePort) -> None:
        self._feature_store = feature_store

    def materialize_window(self, start_date: datetime, end_date: datetime) -> OnlinePipelineResult:
        if start_date >= end_date:
            raise FeatureStoreError(
                "materialization window is empty or inverted",
                context={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )
        self._feature_store.materialize(start_date, end_date)
        return OnlinePipelineResult(start_date=start_date, end_date=end_date)

    def materialize_recent(self, lookback: timedelta) -> OnlinePipelineResult:
        """Materialize ``[now - lookback, now)`` -- the common "catch the
        online store up on anything new" case used by a scheduled
        materialization run."""
        end = datetime.now(UTC)
        start = end - lookback
        return self.materialize_window(start, end)


async def run_online_materialization(*, lookback_hours: float = 24.0) -> dict[str, str]:
    """Convenience entry point mirroring ``offline_pipeline.run_batch_feature_generation``'s
    shape, for a scheduler job or CLI invocation that wants to trigger
    materialization directly."""
    from config.settings import get_settings
    from feature_engineering.feature_store_client import FeastFeatureStoreClient

    settings = get_settings()
    client = FeastFeatureStoreClient(settings)
    pipeline = OnlineFeaturePipeline(client)
    result = pipeline.materialize_recent(timedelta(hours=lookback_hours))
    _logger.info(
        "online_materialization_completed",
        extra={
            "channel": "application",
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
        },
    )
    return {"start_date": result.start_date.isoformat(), "end_date": result.end_date.isoformat()}


__all__ = ["OnlineFeaturePipeline", "OnlinePipelineResult", "run_online_materialization"]
