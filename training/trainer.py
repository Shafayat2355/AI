"""Orchestrates a single training run: load data, fit model, evaluate.

:class:`ModelTrainer` is the concrete orchestration; :func:`run_training_job`
is the integration point ``scheduler/jobs/nightly_training_job.py`` already
calls. A training run always: (1) loads OHLCV history for the configured
symbol(s), (2) builds a labeled dataset via
``datasets.loaders.training_dataset_loader.TrainingDatasetLoader`` (which
retrieves point-in-time-correct historical features from Feast, per Phase
11), (3) splits it chronologically, (4) fits the baseline model, (5) evaluates
on validation and test splits, (6) stores the artifact and registers a new
model version, recording every input needed to reproduce the run (Phase 12's
reproducibility requirement).
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import sklearn

from config.settings import Settings
from core.domain.entities.model_version import (
    EvaluationMetrics,
    ModelLifecycleState,
    ModelVersion,
    TrainingConfig,
    TrainingRun,
)
from core.domain.entities.tick import OHLCVBar
from core.ports.feature_store_port import FeatureStorePort
from core.ports.model_artifact_store_port import ModelArtifactStorePort
from core.ports.model_registry_port import ModelRegistryPort
from datasets.historical.ohlcv_store import INTERVAL_TIMEDELTA, OHLCVStore, SyntheticHistoryConfig
from datasets.loaders.training_dataset_loader import TrainingDataset, TrainingDatasetLoader
from models.model_definitions.lstm_price_model import BaselineDirectionModel
from shared.errors.exceptions import TrainingError
from shared.logging.logger import get_logger
from training.validation import ModelEvaluator, meets_promotion_criteria

_logger = get_logger("training.trainer")


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Chronologically-ordered train/validation/test partitions of one
    :class:`~datasets.loaders.training_dataset_loader.TrainingDataset`.

    Split *chronologically*, never shuffled -- shuffling a time series before
    splitting would let the model train on rows that occur after some of its
    own validation/test rows, which is a subtler form of the same lookahead
    leakage Phase 11's point-in-time retrieval already guards against at the
    feature level.
    """

    train_features: pd.DataFrame
    train_labels: pd.Series
    validation_features: pd.DataFrame
    validation_labels: pd.Series
    test_features: pd.DataFrame
    test_labels: pd.Series


def chronological_split(
    dataset: TrainingDataset, *, train_split: float, validation_split: float
) -> DatasetSplit:
    """Split ``dataset.frame`` (already sorted by ``event_timestamp`` by
    construction) into train/validation/test by position, not by shuffling."""
    frame = dataset.frame.sort_values("event_timestamp").reset_index(drop=True)
    n = len(frame)
    train_end = int(n * train_split)
    validation_end = train_end + int(n * validation_split)

    if train_end == 0 or validation_end == train_end or validation_end >= n:
        raise TrainingError(
            "dataset is too small to split into non-empty train/validation/test partitions",
            context={"rows": n, "train_split": train_split, "validation_split": validation_split},
        )

    feature_columns = list(dataset.feature_columns)
    train = frame.iloc[:train_end]
    validation = frame.iloc[train_end:validation_end]
    test = frame.iloc[validation_end:]

    return DatasetSplit(
        train_features=train[feature_columns],
        train_labels=train["label"],
        validation_features=validation[feature_columns],
        validation_labels=validation["label"],
        test_features=test[feature_columns],
        test_labels=test["label"],
    )


@dataclass(frozen=True, slots=True)
class TrainingResult:
    training_run_id: UUID
    model_version: ModelVersion
    validation_metrics: EvaluationMetrics
    test_metrics: EvaluationMetrics
    promotable: bool


class ModelTrainer:
    """Orchestrates one end-to-end training run for one symbol, against
    injected ports -- no dependency on any concrete Feast/Postgres/filesystem
    adapter, matching every other class in ``training``/``inference``."""

    def __init__(
        self,
        *,
        feature_store: FeatureStorePort,
        model_registry: ModelRegistryPort,
        artifact_store: ModelArtifactStorePort,
        settings: Settings,
    ) -> None:
        self._feature_store = feature_store
        self._model_registry = model_registry
        self._artifact_store = artifact_store
        self._settings = settings
        self._dataset_loader = TrainingDatasetLoader(feature_store)
        self._evaluator = ModelEvaluator()

    async def train(
        self,
        model_name: str,
        symbol: str,
        bars: list[OHLCVBar],
        *,
        dataset_start: datetime,
        dataset_end: datetime,
    ) -> TrainingResult:
        training_settings = self._settings.training
        training_run_id = uuid4()
        started_at = datetime.now(UTC)

        dataset = self._dataset_loader.build(
            symbol, bars, label_horizon=training_settings.label_horizon_bars
        )
        split = chronological_split(
            dataset,
            train_split=training_settings.train_split,
            validation_split=training_settings.validation_split,
        )

        model = BaselineDirectionModel(
            n_estimators=training_settings.n_estimators,
            max_depth=training_settings.max_depth,
            learning_rate=training_settings.learning_rate,
            random_seed=training_settings.random_seed,
        )
        model.fit(split.train_features, split.train_labels)

        validation_metrics = self._evaluator.evaluate(
            model, split.validation_features, split.validation_labels, split="validation"
        )
        test_metrics = self._evaluator.evaluate(
            model, split.test_features, split.test_labels, split="test"
        )

        config = TrainingConfig(
            random_seed=training_settings.random_seed,
            feature_refs=dataset.feature_refs,
            dataset_start=dataset_start,
            dataset_end=dataset_end,
            train_split=training_settings.train_split,
            validation_split=training_settings.validation_split,
            test_split=training_settings.test_split,
            hyperparameters={
                "n_estimators": training_settings.n_estimators,
                "max_depth": training_settings.max_depth,
                "learning_rate": training_settings.learning_rate,
            },
            library_versions={
                "python": platform.python_version(),
                "scikit-learn": sklearn.__version__,
                "numpy": np.__version__,
                "pandas": pd.__version__,
            },
        )
        await self._model_registry.create_training_run(
            TrainingRun(
                id=training_run_id,
                model_name=model_name,
                config=config,
                started_at=started_at,
                status=ModelLifecycleState.CREATED,
            )
        )

        try:
            # Reserve the version number atomically before writing the artifact
            # at its final path.
            version = await self._model_registry.reserve_version(model_name)
            artifact_uri = self._artifact_store.save(model_name, version, model.serialize())
            model_version = await self._model_registry.register_version(
                model_name=model_name,
                version=version,
                artifact_uri=artifact_uri,
                training_run_id=training_run_id,
                feature_refs=dataset.feature_refs,
                config=config,
            )
            model_version = await self._model_registry.record_evaluation(
                model_version.id, validation_metrics
            )
            model_version = await self._model_registry.record_evaluation(
                model_version.id, test_metrics
            )
            await self._model_registry.complete_training_run(training_run_id, model_version.id)
        except Exception as exc:
            try:
                await self._model_registry.fail_training_run(training_run_id, str(exc))
            except Exception:
                _logger.exception("training_run_failure_not_recorded")
            raise

        promotable = meets_promotion_criteria(test_metrics, training_settings)

        _logger.info(
            "training_run_completed",
            extra={
                "channel": "application",
                "training_run_id": str(training_run_id),
                "model_name": model_name,
                "model_version": model_version.version,
                "artifact_uri": artifact_uri,
                "test_accuracy": test_metrics.accuracy,
                "test_f1": test_metrics.f1_score,
                "promotable": promotable,
                "duration_seconds": (datetime.now(UTC) - started_at).total_seconds(),
            },
        )

        return TrainingResult(
            training_run_id=training_run_id,
            model_version=model_version,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            promotable=promotable,
        )


async def run_training_job(
    *,
    model_name: str | None = None,
    symbol: str | None = None,
) -> dict[str, object]:
    """Integration point called by ``scheduler.jobs.nightly_training_job``.

    Resolves its own dependencies from the process
    :class:`~core.container.Container` (matching every other integration
    point's convention -- see
    ``datasets.historical.ohlcv_store.sync_latest_history``), loads history
    for ``symbol`` (default: the first symbol in
    ``datasets.historical.ohlcv_store.SyntheticHistoryConfig``), and runs one
    training run via :class:`ModelTrainer`. Publishes ``training_started``/
    ``training_completed``/``training_failed``/``model_registered`` events on
    ``shared.messaging.topics.MODEL_LIFECYCLE``.

    Raises :class:`~shared.errors.exceptions.TrainingError` on failure, which
    ``call_integration_point`` surfaces as a failed job run.
    """
    from config.settings import get_settings
    from core.container import get_container
    from models.registry_client import PostgresModelRegistry
    from shared.messaging.events import ModelLifecycleEvent
    from shared.messaging.topics import MODEL_LIFECYCLE

    settings = get_settings()
    resolved_model_name = model_name or settings.ai_models.default_model_name
    history_config = SyntheticHistoryConfig()
    resolved_symbol = symbol or history_config.symbols[0]

    container = get_container()
    producer = container.kafka_producer

    async def _publish(transition: str, extra: dict[str, object] | None = None) -> None:
        try:
            await producer.publish(
                MODEL_LIFECYCLE,
                ModelLifecycleEvent(
                    source_service="training",
                    payload={
                        "model_name": resolved_model_name,
                        "transition": transition,
                        **(extra or {}),
                    },
                ),
                key=resolved_model_name,
            )
        except Exception:  # pragma: no cover - best-effort; never fail training over messaging
            _logger.warning(
                "model_lifecycle_event_publish_failed",
                extra={"channel": "application", "transition": transition},
            )

    await _publish("training_started")

    end = datetime.now(UTC)
    start = (
        end
        - INTERVAL_TIMEDELTA[history_config.interval]
        * settings.training.scheduled_training_lookback_bars
    )

    try:
        artifact_store = container.artifact_store
        result: TrainingResult | None = None
        async for session in container.db.session():
            store = OHLCVStore(session)
            bars = await store.get_history(resolved_symbol, history_config.interval, start, end)
            if not bars:
                raise TrainingError(
                    f"no OHLCV history available for {resolved_symbol}; "
                    f"run datasets.historical.ohlcv_store.sync_latest_history first"
                )

            registry = PostgresModelRegistry(session)
            trainer = ModelTrainer(
                feature_store=container.feature_store,
                model_registry=registry,
                artifact_store=artifact_store,
                settings=settings,
            )
            result = await trainer.train(
                resolved_model_name, resolved_symbol, bars, dataset_start=start, dataset_end=end
            )
            await session.commit()
    except Exception as exc:
        await _publish("training_failed", {"error": str(exc)})
        raise TrainingError(f"training run failed for {resolved_model_name}: {exc}") from exc

    assert result is not None
    await _publish(
        "training_completed",
        {"model_version": result.model_version.version, "promotable": result.promotable},
    )
    await _publish("model_registered", {"model_version": result.model_version.version})

    return {
        "model_name": resolved_model_name,
        "symbol": resolved_symbol,
        "training_run_id": str(result.training_run_id),
        "model_version": result.model_version.version,
        "test_accuracy": result.test_metrics.accuracy,
        "test_f1": result.test_metrics.f1_score,
        "promotable": result.promotable,
    }


__all__ = [
    "DatasetSplit",
    "ModelTrainer",
    "TrainingResult",
    "chronological_split",
    "run_training_job",
]
