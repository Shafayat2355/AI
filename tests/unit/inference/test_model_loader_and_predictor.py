"""Unit tests for ``inference/model_loader.py`` and ``inference/predictor.py``.

Both are exercised against small in-test port implementations rather than
mock objects, keeping the tests honest about
``ModelRegistryPort``/``ModelArtifactStorePort``/``FeatureStorePort``'s actual
contracts. The Postgres/Feast-backed implementations are covered by the
integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import pytest

from core.domain.entities.model_version import (
    EvaluationMetrics,
    ModelLifecycleState,
    ModelVersion,
    TrainingConfig,
    TrainingRun,
)
from core.ports.event_publisher_port import EventPublisherPort
from core.ports.feature_store_port import FeatureStorePort
from core.ports.model_artifact_store_port import ModelArtifactStorePort
from core.ports.model_registry_port import ModelRegistryPort
from inference.model_loader import ModelLoader
from inference.predictor import Predictor
from models.model_definitions.lstm_price_model import BaselineDirectionModel
from shared.errors.exceptions import FeatureValidationError, ModelRegistryError

_FEATURE_REFS = ("technical_indicators:sma_20", "technical_indicators:rsi_14")


def _fitted_model_bytes() -> bytes:
    rng = np.random.default_rng(0)
    n = 200
    a = rng.normal(0, 1, n)
    b = rng.normal(0, 1, n)
    model = BaselineDirectionModel(random_seed=42)
    model.fit(pd.DataFrame({"sma_20": a, "rsi_14": b}), pd.Series((a + b > 0).astype(int)))
    return model.serialize()


class _InMemoryArtifactStore(ModelArtifactStorePort):
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, model_name: str, version: int, artifact_bytes: bytes) -> str:
        uri = f"memory://{model_name}/{version}"
        self._data[uri] = artifact_bytes
        return uri

    def load(self, artifact_uri: str) -> bytes:
        if artifact_uri not in self._data:
            raise ModelRegistryError(f"absent: {artifact_uri}")
        return self._data[artifact_uri]

    def delete(self, artifact_uri: str) -> None:
        self._data.pop(artifact_uri, None)

    def exists(self, artifact_uri: str) -> bool:
        return artifact_uri in self._data


class _InMemoryRegistry(ModelRegistryPort):
    def __init__(self) -> None:
        self.versions: dict[UUID, ModelVersion] = {}

    def add(self, version: ModelVersion) -> ModelVersion:
        self.versions[version.id] = version
        return version

    async def create_training_run(self, run: TrainingRun) -> TrainingRun:
        return run

    async def complete_training_run(self, run_id: UUID, model_version_id: UUID) -> TrainingRun:
        raise NotImplementedError

    async def fail_training_run(self, run_id: UUID, error_message: str) -> TrainingRun:
        raise NotImplementedError

    async def reserve_version(self, model_name: str) -> int:
        existing = [v.version for v in self.versions.values() if v.model_name == model_name]
        return (max(existing) if existing else 0) + 1

    async def register_version(self, **kwargs: Any) -> ModelVersion:
        raise NotImplementedError

    async def record_evaluation(
        self, version_id: UUID, metrics: EvaluationMetrics
    ) -> ModelVersion:
        raise NotImplementedError

    async def get_version(self, version_id: UUID) -> ModelVersion | None:
        return self.versions.get(version_id)

    async def get_production_version(self, model_name: str) -> ModelVersion | None:
        return next(
            (
                v
                for v in self.versions.values()
                if v.model_name == model_name and v.stage is ModelLifecycleState.PRODUCTION
            ),
            None,
        )

    async def list_versions(
        self, model_name: str, *, stage: ModelLifecycleState | None = None
    ) -> list[ModelVersion]:
        return [
            v
            for v in self.versions.values()
            if v.model_name == model_name and (stage is None or v.stage is stage)
        ]

    async def promote_version(self, version_id: UUID) -> ModelVersion:
        raise NotImplementedError

    async def rollback_production(self, model_name: str) -> ModelVersion:
        raise NotImplementedError

    async def archive_version(self, version_id: UUID) -> ModelVersion:
        raise NotImplementedError


class _StubFeatureStore(FeatureStorePort):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values if values is not None else {"sma_20": 0.5, "rsi_14": 0.5}

    def get_historical_features(
        self, entity_df: pd.DataFrame, feature_refs: list[str] | None = None
    ) -> pd.DataFrame:
        raise NotImplementedError

    def get_online_features(
        self, entity_rows: list[dict[str, Any]], feature_refs: list[str] | None = None
    ) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {"symbol": [r["symbol"] for r in entity_rows]}
        for key, value in self.values.items():
            out[key] = [value] * len(entity_rows)
        return out

    def materialize(self, start_date: datetime, end_date: datetime) -> None:
        return None

    def apply(self) -> None:
        return None


def _version(
    *, stage: ModelLifecycleState, artifact_uri: str, version: int = 1
) -> ModelVersion:
    return ModelVersion(
        id=uuid4(),
        model_name="baseline-momentum",
        version=version,
        stage=stage,
        artifact_uri=artifact_uri,
        training_run_id=uuid4(),
        feature_refs=_FEATURE_REFS,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def wired() -> tuple[_InMemoryRegistry, _InMemoryArtifactStore, ModelVersion]:
    registry = _InMemoryRegistry()
    store = _InMemoryArtifactStore()
    uri = store.save("baseline-momentum", 1, _fitted_model_bytes())
    version = registry.add(_version(stage=ModelLifecycleState.PRODUCTION, artifact_uri=uri))
    return registry, store, version


class TestModelLoader:
    async def test_loads_the_production_version(self, wired) -> None:
        registry, store, version = wired
        loaded = await ModelLoader(registry, store).load_production("baseline-momentum")
        assert loaded.version.id == version.id
        assert isinstance(loaded.model, BaselineDirectionModel)

    async def test_loaded_model_produces_real_predictions(self, wired) -> None:
        registry, store, _ = wired
        loaded = await ModelLoader(registry, store).load_production("baseline-momentum")
        probability = loaded.model.predict_proba(
            pd.DataFrame([{"sma_20": 1.0, "rsi_14": 1.0}])
        )[0]
        assert 0.0 <= probability <= 1.0

    async def test_raises_when_no_production_version_exists(self) -> None:
        loader = ModelLoader(_InMemoryRegistry(), _InMemoryArtifactStore())
        with pytest.raises(ModelRegistryError, match="no production version"):
            await loader.load_production("baseline-momentum")

    async def test_loads_a_specific_version_regardless_of_stage(self) -> None:
        registry, store = _InMemoryRegistry(), _InMemoryArtifactStore()
        uri = store.save("baseline-momentum", 2, _fitted_model_bytes())
        staged = registry.add(
            _version(stage=ModelLifecycleState.STAGED, artifact_uri=uri, version=2)
        )
        loaded = await ModelLoader(registry, store).load_version(staged.id)
        assert loaded.version.version == 2

    async def test_raises_for_an_unknown_version_id(self) -> None:
        loader = ModelLoader(_InMemoryRegistry(), _InMemoryArtifactStore())
        with pytest.raises(ModelRegistryError, match="not found"):
            await loader.load_version(uuid4())

    async def test_propagates_a_missing_artifact_as_a_typed_error(self) -> None:
        registry, store = _InMemoryRegistry(), _InMemoryArtifactStore()
        registry.add(
            _version(stage=ModelLifecycleState.PRODUCTION, artifact_uri="memory://gone/1")
        )
        with pytest.raises(ModelRegistryError, match="absent"):
            await ModelLoader(registry, store).load_production("baseline-momentum")


class TestPredictor:
    async def test_returns_a_real_prediction_with_model_metadata(self, wired) -> None:
        registry, store, version = wired
        predictor = Predictor(ModelLoader(registry, store), _StubFeatureStore())
        result = await predictor.predict("baseline-momentum", "BTCUSDT")

        assert result.symbol == "BTCUSDT"
        assert result.predicted_class in (0, 1)
        assert 0.0 <= result.probability_up <= 1.0
        assert result.model_version == version.version
        assert result.model_name == "baseline-momentum"
        assert result.predicted_at.tzinfo is not None

    async def test_predicted_class_agrees_with_the_probability_threshold(self, wired) -> None:
        registry, store, _ = wired
        predictor = Predictor(ModelLoader(registry, store), _StubFeatureStore())
        result = await predictor.predict("baseline-momentum", "BTCUSDT")
        assert result.predicted_class == int(result.probability_up >= 0.5)

    async def test_different_feature_inputs_can_change_the_prediction(self, wired) -> None:
        """Guards against a hardcoded/constant prediction path -- Phase 12
        explicitly forbids one."""
        registry, store, _ = wired
        loader = ModelLoader(registry, store)
        low = await Predictor(
            loader, _StubFeatureStore({"sma_20": -3.0, "rsi_14": -3.0})
        ).predict("baseline-momentum", "BTCUSDT")
        high = await Predictor(
            loader, _StubFeatureStore({"sma_20": 3.0, "rsi_14": 3.0})
        ).predict("baseline-momentum", "BTCUSDT")
        assert low.probability_up != high.probability_up

    async def test_rejects_a_payload_missing_a_required_feature(self, wired) -> None:
        registry, store, _ = wired
        predictor = Predictor(
            ModelLoader(registry, store), _StubFeatureStore({"sma_20": 0.5})
        )
        with pytest.raises(FeatureValidationError, match="missing features"):
            await predictor.predict("baseline-momentum", "BTCUSDT")

    async def test_rejects_an_unmaterialized_null_feature_payload(self, wired) -> None:
        registry, store, _ = wired
        predictor = Predictor(
            ModelLoader(registry, store),
            _StubFeatureStore({"sma_20": None, "rsi_14": 0.5}),
        )
        with pytest.raises(FeatureValidationError, match="unset"):
            await predictor.predict("baseline-momentum", "BTCUSDT")

    async def test_publishes_a_prediction_event_when_a_publisher_is_wired(self, wired) -> None:
        registry, store, _ = wired
        published: list[tuple[Any, Any]] = []

        class _Publisher(EventPublisherPort):
            async def publish(self, topic, event, key=None):  # noqa: ANN001, ANN202
                published.append((topic, event))

        predictor = Predictor(ModelLoader(registry, store), _StubFeatureStore(), _Publisher())
        result = await predictor.predict("baseline-momentum", "BTCUSDT")

        assert len(published) == 1
        _, event = published[0]
        assert event.payload["symbol"] == "BTCUSDT"
        assert event.payload["model_version"] == result.model_version

    async def test_a_failing_publisher_does_not_fail_the_prediction(self, wired) -> None:
        registry, store, _ = wired

        class _BrokenPublisher(EventPublisherPort):
            async def publish(self, topic, event, key=None):  # noqa: ANN001, ANN202
                raise RuntimeError("kafka down")

        predictor = Predictor(
            ModelLoader(registry, store), _StubFeatureStore(), _BrokenPublisher()
        )
        result = await predictor.predict("baseline-momentum", "BTCUSDT")
        assert result.predicted_class in (0, 1)
