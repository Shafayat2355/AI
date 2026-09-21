"""Client implementing core/ports/feature_store_port.py for reading/writing
feature values.

Backed by Feast (0.66+), constructed from this platform's own ``Settings``
via ``feature_engineering/feast_repo/repo_builder.py`` -- see that module's
docstring for why there is no checked-in ``feature_store.yaml``.
:class:`FeastFeatureStoreClient` is the *only* module in this codebase that
imports ``feast`` directly; every other caller (``training/trainer.py``,
``inference/predictor.py``) depends on ``core.ports.feature_store_port.FeatureStorePort``
instead, per that port's own hexagonal-boundary docstring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from feast import FeatureStore

from config.settings import Settings
from core.ports.feature_store_port import FeatureStorePort
from feature_engineering.feast_repo.entities import SYMBOL
from feature_engineering.feast_repo.feature_views import all_feature_refs, build_feature_views
from feature_engineering.feast_repo.repo_builder import build_repo_config
from shared.errors.exceptions import FeatureStoreError
from shared.logging.logger import get_logger

_logger = get_logger("feature_engineering.feature_store_client")


class FeastFeatureStoreClient(FeatureStorePort):
    """Feast-backed implementation of :class:`~core.ports.feature_store_port.FeatureStorePort`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        try:
            self._store = FeatureStore(config=build_repo_config(settings))
        except Exception as exc:
            raise FeatureStoreError(f"failed to construct Feast FeatureStore: {exc}") from exc

    def apply(self) -> None:
        try:
            technical_view, statistical_view = build_feature_views(
                self._settings.feature_engineering.offline_store_path
            )
            self._store.apply([SYMBOL, technical_view, statistical_view])
        except Exception as exc:
            raise FeatureStoreError(f"failed to apply Feast feature definitions: {exc}") from exc
        _logger.info(
            "feature_store_definitions_applied",
            extra={"channel": "application", "project": self._store.project},
        )

    def get_historical_features(
        self,
        entity_df: pd.DataFrame,
        feature_refs: list[str] | None = None,
    ) -> pd.DataFrame:
        refs = feature_refs or all_feature_refs()
        try:
            job = self._store.get_historical_features(entity_df=entity_df, features=refs)
            return job.to_df()
        except Exception as exc:
            raise FeatureStoreError(
                f"historical feature retrieval failed: {exc}",
                context={"feature_refs": refs, "rows_requested": len(entity_df)},
            ) from exc

    def get_online_features(
        self,
        entity_rows: list[dict[str, Any]],
        feature_refs: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        refs = feature_refs or all_feature_refs()
        try:
            response = self._store.get_online_features(features=refs, entity_rows=entity_rows)
            return response.to_dict()
        except Exception as exc:
            raise FeatureStoreError(
                f"online feature retrieval failed: {exc}",
                context={"feature_refs": refs, "rows_requested": len(entity_rows)},
            ) from exc

    def materialize(self, start_date: datetime, end_date: datetime) -> None:
        try:
            self._store.materialize(start_date=start_date, end_date=end_date)
        except Exception as exc:
            raise FeatureStoreError(
                f"materialization failed: {exc}",
                context={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            ) from exc
        _logger.info(
            "feature_store_materialized",
            extra={
                "channel": "application",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )


__all__ = ["FeastFeatureStoreClient"]
