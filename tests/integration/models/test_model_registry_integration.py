"""Integration test: ``models.registry_client.PostgresModelRegistry`` against a
real (in-memory SQLite) database.

The registry's whole job is persistence and lifecycle-state enforcement, so
mocking the database away would test nothing -- this follows
``tests/integration/database/test_mixins_and_unit_of_work_integration.py``'s
precedent of driving real SQLAlchemy against SQLite.

Infrastructure note: SQLite is used rather than PostgreSQL so the suite runs
without external services. The mapped models are backend-agnostic (``Uuid``,
``JSON``, ``DateTime(timezone=True)``), and the Alembic migration is verified
separately in ``tests/integration/database/``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.domain.entities.model_version import (
    EvaluationMetrics,
    ModelLifecycleState,
    TrainingConfig,
)
from database.base import Base
from models.registry_client import PostgresModelRegistry, TrainingRunModel
from shared.errors.exceptions import ModelRegistryError, ModelStateError

_MODEL = "baseline-momentum"
_REFS = ("technical_indicators:sma_20",)


def _config() -> TrainingConfig:
    return TrainingConfig(
        random_seed=42,
        feature_refs=_REFS,
        dataset_start=datetime(2026, 1, 1, tzinfo=UTC),
        dataset_end=datetime(2026, 2, 1, tzinfo=UTC),
        train_split=0.7,
        validation_split=0.15,
        test_split=0.15,
        hyperparameters={"n_estimators": 10},
        library_versions={"python": "3.12.0"},
    )


def _metrics(split: str, *, accuracy: float = 0.6, f1: float = 0.55) -> EvaluationMetrics:
    return EvaluationMetrics(
        split=split,
        accuracy=accuracy,
        precision=0.6,
        recall=0.5,
        f1_score=f1,
        sample_count=100,
        evaluated_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def _training_run(session: AsyncSession):  # noqa: ANN202
    run = TrainingRunModel(
        model_name=_MODEL,
        status=ModelLifecycleState.TRAINED.value,
        random_seed=42,
        feature_refs=list(_REFS),
        dataset_start=datetime(2026, 1, 1, tzinfo=UTC),
        dataset_end=datetime(2026, 2, 1, tzinfo=UTC),
        train_split=0.7,
        validation_split=0.15,
        test_split=0.15,
        hyperparameters={},
        library_versions={},
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    return run


async def _register(session: AsyncSession, registry: PostgresModelRegistry):  # noqa: ANN202
    run = await _training_run(session)
    version_number = await registry.reserve_version(_MODEL)
    return await registry.register_version(
        model_name=_MODEL,
        version=version_number,
        artifact_uri=f"file:///tmp/{_MODEL}/{version_number}/model.bin",
        training_run_id=run.id,
        feature_refs=_REFS,
        config=_config(),
    )


async def _promote_fresh(session: AsyncSession, registry: PostgresModelRegistry):  # noqa: ANN202
    version = await _register(session, registry)
    await registry.record_evaluation(version.id, _metrics("test"))
    return await registry.promote_version(version.id)


class TestRegisterAndVersioning:
    async def test_assigns_version_one_to_the_first_registration(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        assert (await _register(session, registry)).version == 1

    async def test_assigns_monotonically_increasing_versions(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        assert (await _register(session, registry)).version == 1
        assert (await _register(session, registry)).version == 2
        assert (await _register(session, registry)).version == 3

    async def test_a_new_version_starts_in_trained_state(self, session: AsyncSession) -> None:
        registry = PostgresModelRegistry(session)
        assert (await _register(session, registry)).stage is ModelLifecycleState.TRAINED

    async def test_persists_the_feature_refs_the_model_was_trained_on(
        self, session: AsyncSession
    ) -> None:
        """Training/serving consistency depends on this being recorded."""
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        fetched = await registry.get_version(version.id)
        assert fetched is not None
        assert fetched.feature_refs == _REFS

    async def test_get_version_returns_none_for_an_unknown_id(
        self, session: AsyncSession
    ) -> None:
        assert await PostgresModelRegistry(session).get_version(uuid4()) is None


class TestEvaluation:
    async def test_recording_test_metrics_advances_trained_to_validated(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        updated = await registry.record_evaluation(version.id, _metrics("test"))
        assert updated.stage is ModelLifecycleState.VALIDATED

    async def test_recording_validation_metrics_alone_does_not_advance_state(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        updated = await registry.record_evaluation(version.id, _metrics("validation"))
        assert updated.stage is ModelLifecycleState.TRAINED

    async def test_metrics_are_retrievable_with_the_version(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        await registry.record_evaluation(version.id, _metrics("validation", accuracy=0.61))
        await registry.record_evaluation(version.id, _metrics("test", accuracy=0.62))

        fetched = await registry.get_version(version.id)
        assert fetched is not None
        assert fetched.validation_metrics is not None
        assert fetched.test_metrics is not None
        assert fetched.validation_metrics.accuracy == pytest.approx(0.61)
        assert fetched.test_metrics.accuracy == pytest.approx(0.62)

    async def test_evaluating_an_unknown_version_raises(self, session: AsyncSession) -> None:
        with pytest.raises(ModelRegistryError, match="not found"):
            await PostgresModelRegistry(session).record_evaluation(uuid4(), _metrics("test"))


class TestPromotion:
    async def test_promotes_a_validated_version_to_production(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        promoted = await _promote_fresh(session, registry)
        assert promoted.stage is ModelLifecycleState.PRODUCTION
        assert promoted.promoted_at is not None

    async def test_refuses_to_promote_a_version_that_has_not_been_evaluated(
        self, session: AsyncSession
    ) -> None:
        """A model must not reach production without passing evaluation."""
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        with pytest.raises(ModelStateError, match="cannot promote"):
            await registry.promote_version(version.id)

    async def test_promoting_a_replacement_archives_the_previous_champion(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        first = await _promote_fresh(session, registry)
        second = await _promote_fresh(session, registry)

        assert second.stage is ModelLifecycleState.PRODUCTION
        archived = await registry.get_version(first.id)
        assert archived is not None
        assert archived.stage is ModelLifecycleState.ARCHIVED

    async def test_exactly_one_version_is_in_production_at_a_time(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        await _promote_fresh(session, registry)
        await _promote_fresh(session, registry)
        await _promote_fresh(session, registry)

        in_production = await registry.list_versions(
            _MODEL, stage=ModelLifecycleState.PRODUCTION
        )
        assert len(in_production) == 1

    async def test_refuses_to_promote_an_archived_version(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        first = await _promote_fresh(session, registry)
        await _promote_fresh(session, registry)  # archives `first`
        with pytest.raises(ModelStateError, match="cannot promote"):
            await registry.promote_version(first.id)


class TestRollback:
    async def test_restores_the_previous_champion(self, session: AsyncSession) -> None:
        registry = PostgresModelRegistry(session)
        first = await _promote_fresh(session, registry)
        second = await _promote_fresh(session, registry)

        rolled_back = await registry.rollback_production(_MODEL)
        assert rolled_back.id == first.id
        assert rolled_back.stage is ModelLifecycleState.PRODUCTION
        demoted = await registry.get_version(second.id)
        assert demoted is not None
        assert demoted.stage is ModelLifecycleState.ARCHIVED

    async def test_rollback_leaves_exactly_one_production_version(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        await _promote_fresh(session, registry)
        await _promote_fresh(session, registry)
        await registry.rollback_production(_MODEL)

        assert len(await registry.list_versions(_MODEL, stage=ModelLifecycleState.PRODUCTION)) == 1

    async def test_refuses_rollback_when_nothing_is_in_production(
        self, session: AsyncSession
    ) -> None:
        with pytest.raises(ModelStateError, match="no current production version"):
            await PostgresModelRegistry(session).rollback_production(_MODEL)

    async def test_refuses_rollback_when_there_is_no_prior_champion(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        await _promote_fresh(session, registry)
        with pytest.raises(ModelStateError, match="no prior production version"):
            await registry.rollback_production(_MODEL)


class TestArchiving:
    async def test_archives_a_non_production_version(self, session: AsyncSession) -> None:
        registry = PostgresModelRegistry(session)
        version = await _register(session, registry)
        archived = await registry.archive_version(version.id)
        assert archived.stage is ModelLifecycleState.ARCHIVED
        assert archived.archived_at is not None

    async def test_refuses_to_archive_the_current_production_version(
        self, session: AsyncSession
    ) -> None:
        """Otherwise a model could be left with no production version silently."""
        registry = PostgresModelRegistry(session)
        promoted = await _promote_fresh(session, registry)
        with pytest.raises(ModelStateError, match="cannot archive"):
            await registry.archive_version(promoted.id)


class TestListing:
    async def test_lists_versions_newest_first(self, session: AsyncSession) -> None:
        registry = PostgresModelRegistry(session)
        await _register(session, registry)
        await _register(session, registry)
        assert [v.version for v in await registry.list_versions(_MODEL)] == [2, 1]

    async def test_filters_by_stage(self, session: AsyncSession) -> None:
        registry = PostgresModelRegistry(session)
        await _register(session, registry)
        await _promote_fresh(session, registry)
        trained = await registry.list_versions(_MODEL, stage=ModelLifecycleState.TRAINED)
        assert [v.version for v in trained] == [1]

    async def test_does_not_leak_versions_of_other_models(
        self, session: AsyncSession
    ) -> None:
        registry = PostgresModelRegistry(session)
        await _register(session, registry)
        assert await registry.list_versions("some-other-model") == []
