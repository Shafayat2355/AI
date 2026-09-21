"""Integration test: the complete Phase 12 pipeline, end to end, with real
infrastructure at every layer except Kafka.

Wires together real synthetic OHLCV history -> real feature computation ->
a real Feast store -> a real SQLite-backed model registry -> a real
filesystem artifact store -> real training -> real promotion -> real
inference. Nothing in this path is mocked, which is what makes it capable of
catching the wiring bugs the unit suites structurally cannot.

Infrastructure notes:
* Online store is Feast's ``sqlite`` backend, not Redis (Phase 8) -- see
  ``tests/integration/feature_engineering/`` for the same caveat.
* Registry is SQLite, not PostgreSQL (Phase 7); the Alembic migration itself
  is verified in ``tests/integration/database/``.
* Kafka (Phase 9) is not exercised here; lifecycle-event publication is
  best-effort by design and covered by the unit suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.modules.feature_engineering import FeatureEngineeringSettings
from config.modules.training import TrainingSettings
from config.settings import Settings
from core.domain.entities.model_version import ModelLifecycleState
from database.base import Base
from datasets.historical.ohlcv_store import SyntheticHistoryConfig, generate_synthetic_bars
from feature_engineering.feature_store_client import FeastFeatureStoreClient
from feature_engineering.offline_pipeline import OfflineFeaturePipeline
from feature_engineering.online_pipeline import OnlineFeaturePipeline
from inference.model_loader import ModelLoader
from inference.predictor import Predictor
from mlops.promotion_policy import PromotionPolicy
from models.artifact_store import LocalFilesystemArtifactStore
from models.registry_client import PostgresModelRegistry, TrainingRunModel
from training.trainer import ModelTrainer

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)
_SYMBOL = "BTCUSDT"
_MODEL = "baseline-momentum"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        feature_engineering=FeatureEngineeringSettings(
            online_store_backend="sqlite",
            offline_store_path=str(tmp_path / "offline"),
            feast_project_name="training_integration_test",
        ),
        training=TrainingSettings(
            artifact_store_dir=str(tmp_path / "artifacts"),
            n_estimators=10,  # keep the suite fast; mechanics are what matter
            max_depth=2,
            random_seed=42,
            # Thresholds set to 0 so promotion mechanics are exercised
            # deterministically -- this is NOT a claim the baseline is accurate.
            min_promotion_accuracy=0.0,
            min_promotion_f1=0.0,
        ),
    )


@pytest.fixture
def bars():  # noqa: ANN201
    return generate_synthetic_bars(
        _SYMBOL, SyntheticHistoryConfig(symbols=(_SYMBOL,), lookback_bars=600), end_time=_ANCHOR
    )


@pytest.fixture
def feature_store(settings: Settings, bars) -> FeastFeatureStoreClient:  # noqa: ANN001
    OfflineFeaturePipeline(settings.feature_engineering.offline_store_path).run({_SYMBOL: bars})
    client = FeastFeatureStoreClient(settings)
    client.apply()
    OnlineFeaturePipeline(client).materialize_window(
        _ANCHOR - timedelta(days=60), _ANCHOR + timedelta(days=1)
    )
    return client


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as active:
        yield active
    await engine.dispose()


@pytest.fixture
def trainer(
    settings: Settings, feature_store: FeastFeatureStoreClient, session: AsyncSession
) -> ModelTrainer:
    return ModelTrainer(
        feature_store=feature_store,
        model_registry=PostgresModelRegistry(session),
        artifact_store=LocalFilesystemArtifactStore(settings.training.artifact_store_dir),
        settings=settings,
    )


async def _train(trainer: ModelTrainer, bars):  # noqa: ANN001, ANN202
    return await trainer.train(
        _MODEL,
        _SYMBOL,
        bars,
        dataset_start=_ANCHOR - timedelta(days=30),
        dataset_end=_ANCHOR,
    )


class TestTrainingRun:
    async def test_produces_a_registered_versioned_model(self, trainer, bars) -> None:  # noqa: ANN001
        result = await _train(trainer, bars)
        assert result.model_version.version == 1
        assert result.model_version.stage is ModelLifecycleState.VALIDATED

    async def test_records_both_validation_and_test_metrics(self, trainer, bars) -> None:  # noqa: ANN001
        result = await _train(trainer, bars)
        assert result.validation_metrics.split == "validation"
        assert result.test_metrics.split == "test"
        assert result.test_metrics.sample_count > 0

    async def test_metrics_are_real_numbers_in_range(self, trainer, bars) -> None:  # noqa: ANN001
        """Deliberately asserts only validity, not quality -- the baseline
        makes no accuracy claim (see Phase 12 docs, 'Baseline model')."""
        result = await _train(trainer, bars)
        assert 0.0 <= result.test_metrics.accuracy <= 1.0
        assert 0.0 <= result.test_metrics.f1_score <= 1.0

    async def test_writes_a_loadable_artifact_at_the_registered_uri(
        self, trainer, bars, settings: Settings
    ) -> None:  # noqa: ANN001
        """Regression guard: the registry's artifact_uri must point at a file
        that actually exists -- an earlier placeholder-then-rename design left
        this dangling."""
        result = await _train(trainer, bars)
        store = LocalFilesystemArtifactStore(settings.training.artifact_store_dir)
        assert store.exists(result.model_version.artifact_uri)
        assert len(store.load(result.model_version.artifact_uri)) > 0

    async def test_records_the_feature_refs_used(self, trainer, bars) -> None:  # noqa: ANN001
        result = await _train(trainer, bars)
        assert len(result.model_version.feature_refs) > 0

    async def test_persists_and_links_the_training_run(
        self, trainer, bars, session: AsyncSession
    ) -> None:  # noqa: ANN001
        result = await _train(trainer, bars)
        run = await session.get(TrainingRunModel, result.training_run_id)
        assert run is not None
        assert run.model_version_id == result.model_version.id
        assert run.status == ModelLifecycleState.TRAINED.value

    async def test_successive_runs_increment_the_version(self, trainer, bars) -> None:  # noqa: ANN001
        assert (await _train(trainer, bars)).model_version.version == 1
        assert (await _train(trainer, bars)).model_version.version == 2

    async def test_is_reproducible_for_a_fixed_seed(self, trainer, bars) -> None:  # noqa: ANN001
        """Phase 12's reproducibility requirement, asserted end to end."""
        first = await _train(trainer, bars)
        second = await _train(trainer, bars)
        assert first.test_metrics.accuracy == pytest.approx(second.test_metrics.accuracy)
        assert first.test_metrics.f1_score == pytest.approx(second.test_metrics.f1_score)


class TestPromotionAndInference:
    async def test_promotes_a_qualifying_candidate(
        self, trainer, bars, session: AsyncSession, settings: Settings
    ) -> None:  # noqa: ANN001
        await _train(trainer, bars)
        registry = PostgresModelRegistry(session)
        promoted = await PromotionPolicy(registry, settings).evaluate_and_promote(_MODEL)

        assert promoted is not None
        assert promoted.stage is ModelLifecycleState.PRODUCTION

    async def test_rejects_a_candidate_below_threshold(
        self, trainer, bars, session: AsyncSession, settings: Settings
    ) -> None:  # noqa: ANN001
        """A model must not reach production just because training succeeded."""
        await _train(trainer, bars)
        strict = settings.model_copy(
            update={
                "training": settings.training.model_copy(
                    update={"min_promotion_accuracy": 0.99, "min_promotion_f1": 0.99}
                )
            }
        )
        registry = PostgresModelRegistry(session)
        assert await PromotionPolicy(registry, strict).evaluate_and_promote(_MODEL) is None
        assert await registry.get_production_version(_MODEL) is None

    async def test_inference_uses_the_promoted_model_and_reports_its_version(
        self, trainer, bars, session: AsyncSession, settings: Settings, feature_store
    ) -> None:  # noqa: ANN001
        await _train(trainer, bars)
        registry = PostgresModelRegistry(session)
        promoted = await PromotionPolicy(registry, settings).evaluate_and_promote(_MODEL)
        assert promoted is not None

        loader = ModelLoader(
            registry, LocalFilesystemArtifactStore(settings.training.artifact_store_dir)
        )
        result = await Predictor(loader, feature_store).predict(_MODEL, _SYMBOL)

        assert result.model_version == promoted.version
        assert result.predicted_class in (0, 1)
        assert 0.0 <= result.probability_up <= 1.0

    async def test_rollback_restores_the_previous_model_for_inference(
        self, trainer, bars, session: AsyncSession, settings: Settings, feature_store
    ) -> None:  # noqa: ANN001
        """The full failure-recovery path: two promoted versions, roll back,
        and confirm inference actually serves the restored one."""
        registry = PostgresModelRegistry(session)
        policy = PromotionPolicy(registry, settings)

        await _train(trainer, bars)
        first = await policy.evaluate_and_promote(_MODEL)
        assert first is not None
        await _train(trainer, bars)
        second = await policy.evaluate_and_promote(_MODEL)
        assert second is not None
        assert second.version != first.version

        rolled_back = await registry.rollback_production(_MODEL)
        assert rolled_back.version == first.version

        loader = ModelLoader(
            registry, LocalFilesystemArtifactStore(settings.training.artifact_store_dir)
        )
        result = await Predictor(loader, feature_store).predict(_MODEL, _SYMBOL)
        assert result.model_version == first.version
