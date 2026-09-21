"""Runs model inference against online features and publishes prediction events.

:class:`Predictor` retrieves online features for a symbol via
``core.ports.feature_store_port.FeatureStorePort`` (Phase 11, served from
Redis), validates the payload against what the loaded model was trained on,
runs a real prediction (never a hardcoded buy/sell decision, per Phase 12's
explicit requirement), and publishes a
``shared.messaging.events.PredictionEvent`` on
``shared.messaging.topics.PREDICTIONS`` so downstream strategy logic can
consume it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from core.ports.event_publisher_port import EventPublisherPort
from core.ports.feature_store_port import FeatureStorePort
from datasets.schemas.dataset_schema import detect_missing_features
from inference.model_loader import LoadedModel, ModelLoader
from shared.errors.exceptions import FeatureValidationError
from shared.logging.logger import get_logger

_logger = get_logger("inference.predictor")


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """One inference result, including the metadata a consumer needs to
    judge how much to trust it (Phase 12's "prediction metadata including
    model version" requirement)."""

    symbol: str
    predicted_class: int
    probability_up: float
    model_name: str
    model_version: int
    predicted_at: datetime


class Predictor:
    """Runs inference for one symbol against the current production model,
    against injected ports -- no direct Feast/Kafka dependency."""

    def __init__(
        self,
        model_loader: ModelLoader,
        feature_store: FeatureStorePort,
        event_publisher: EventPublisherPort | None = None,
    ) -> None:
        self._model_loader = model_loader
        self._feature_store = feature_store
        self._event_publisher = event_publisher

    async def predict(self, model_name: str, symbol: str) -> PredictionResult:
        loaded = await self._model_loader.load_production(model_name)
        features_df = self._fetch_and_validate_features(loaded, symbol)

        probability_up = float(loaded.model.predict_proba(features_df)[0])
        predicted_class = int(probability_up >= 0.5)

        result = PredictionResult(
            symbol=symbol,
            predicted_class=predicted_class,
            probability_up=probability_up,
            model_name=model_name,
            model_version=loaded.version.version,
            predicted_at=datetime.now(UTC),
        )

        await self._publish(result)
        return result

    def _fetch_and_validate_features(self, loaded: LoadedModel, symbol: str) -> pd.DataFrame:
        online = self._feature_store.get_online_features(
            [{"symbol": symbol}], list(loaded.version.feature_refs)
        )
        row = {key: values[0] for key, values in online.items() if key != "symbol"}
        features_df = pd.DataFrame([row])

        # feature_refs are "<view>:<feature>" but Feast's OnlineResponse keys
        # by the bare feature name -- the model itself was trained on those
        # same bare names (feature_engineering/offline_pipeline.py's output
        # columns), so no reference-name translation is needed here.
        expected_columns = [ref.split(":", 1)[-1] for ref in loaded.version.feature_refs]
        missing = detect_missing_features(features_df, expected_columns)
        if missing:
            raise FeatureValidationError(
                f"online feature payload for {symbol} is missing features the model "
                f"was trained on",
                context={"symbol": symbol, "missing_features": missing},
            )
        if features_df[expected_columns].isna().any(axis=None):
            raise FeatureValidationError(
                f"online feature payload for {symbol} has unset (None) values -- "
                f"the feature store has not been materialized recently enough",
                context={"symbol": symbol},
            )
        return features_df[expected_columns]

    async def _publish(self, result: PredictionResult) -> None:
        if self._event_publisher is None:
            return
        from shared.messaging.events import PredictionEvent
        from shared.messaging.topics import PREDICTIONS

        try:
            await self._event_publisher.publish(
                PREDICTIONS,
                PredictionEvent(
                    source_service="inference",
                    payload={
                        "symbol": result.symbol,
                        "predicted_class": result.predicted_class,
                        "probability_up": result.probability_up,
                        "model_name": result.model_name,
                        "model_version": result.model_version,
                    },
                ),
                key=result.symbol,
            )
        except Exception:  # pragma: no cover - best-effort, matches trainer's convention
            _logger.warning(
                "prediction_event_publish_failed",
                extra={"channel": "application", "symbol": result.symbol},
            )


__all__ = ["PredictionResult", "Predictor"]
