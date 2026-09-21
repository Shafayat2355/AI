"""Client implementing core/ports/model_registry_port.py against PostgreSQL.

Reuses Phase 7's database layer exactly as
``database/repositories/ohlcv_bar_repository.py`` does: mapped models
composing ``database.base.Base`` + ``database.mixins``, no second database
connection layer. Three tables back this client --
``training_runs``/``model_versions``/``model_evaluations`` -- created by
``database/migrations/versions/3d0f3957e9be_phase12_model_registry.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.domain.entities.model_version import (
    EvaluationMetrics,
    ModelLifecycleState,
    ModelVersion,
    TrainingConfig,
    TrainingRun,
)
from core.ports.model_registry_port import ModelRegistryPort
from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from shared.errors.exceptions import ModelRegistryError, ModelStateError
from shared.logging.logger import get_logger

_logger = get_logger("models.registry_client")


class TrainingRunModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One execution of the training pipeline and the exact configuration
    used, for reproducibility (Phase 12's reproducibility requirement)."""

    __tablename__ = "training_runs"

    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dataset_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dataset_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    train_split: Mapped[float] = mapped_column(Float, nullable=False)
    validation_split: Mapped[float] = mapped_column(Float, nullable=False)
    test_split: Mapped[float] = mapped_column(Float, nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    library_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    #: Deliberately a plain UUID column, not a ForeignKey -- model_versions.training_run_id
    #: already points the other way, and a bidirectional FK pair would force an
    #: awkward creation order / deferred constraint in the migration for no
    #: benefit (application code, not the database, is the source of truth for
    #: this one-to-one link once training completes).
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True, default=None)

    def to_entity(self, config: TrainingConfig) -> TrainingRun:
        return TrainingRun(
            id=self.id,
            model_name=self.model_name,
            config=config,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=ModelLifecycleState(self.status),
            model_version_id=self.model_version_id,
            error_message=self.error_message,
        )


class ModelVersionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One registered, versioned model artifact."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_model_versions_name_version"),
    )

    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    training_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_runs.id"), nullable=False
    )
    feature_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    #: Set when this version transitions PRODUCTION -> ARCHIVED, so
    #: rollback_production() can find "the prior champion" rather than just
    #: any archived version.
    was_production: Mapped[bool] = mapped_column(default=False, nullable=False)

    def to_entity(
        self,
        *,
        validation_metrics: EvaluationMetrics | None,
        test_metrics: EvaluationMetrics | None,
    ) -> ModelVersion:
        return ModelVersion(
            id=self.id,
            model_name=self.model_name,
            version=self.version,
            stage=ModelLifecycleState(self.stage),
            artifact_uri=self.artifact_uri,
            training_run_id=self.training_run_id,
            feature_refs=tuple(self.feature_refs),
            created_at=self.created_at,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            promoted_at=self.promoted_at,
            archived_at=self.archived_at,
        )


class ModelEvaluationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One evaluation result (validation or test split) for one model version."""

    __tablename__ = "model_evaluations"

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"), nullable=False
    )
    split: Mapped[str] = mapped_column(String(16), nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    recall: Mapped[float] = mapped_column(Float, nullable=False)
    f1_score: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extra_metrics: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def to_entity(self) -> EvaluationMetrics:
        return EvaluationMetrics(
            split=self.split,
            accuracy=self.accuracy,
            precision=self.precision,
            recall=self.recall,
            f1_score=self.f1_score,
            sample_count=self.sample_count,
            extra_metrics=dict(self.extra_metrics),
            evaluated_at=self.evaluated_at,
        )


class ModelVersionCounterModel(Base):
    """One atomic, per-model version counter.

    ``model_versions`` itself cannot safely be queried and incremented by
    concurrent training transactions.  This row is updated atomically by
    :meth:`PostgresModelRegistry.reserve_version` instead.
    """

    __tablename__ = "model_version_counters"

    model_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    next_version: Mapped[int] = mapped_column(Integer, nullable=False)


class PostgresModelRegistry(ModelRegistryPort):
    """PostgreSQL-backed :class:`~core.ports.model_registry_port.ModelRegistryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _latest_metrics(
        self, version_id: uuid.UUID
    ) -> tuple[EvaluationMetrics | None, EvaluationMetrics | None]:
        result = await self._session.execute(
            select(ModelEvaluationModel)
            .where(ModelEvaluationModel.model_version_id == version_id)
            .order_by(ModelEvaluationModel.evaluated_at.desc())
        )
        rows = result.scalars().all()
        validation = next((r.to_entity() for r in rows if r.split == "validation"), None)
        test = next((r.to_entity() for r in rows if r.split == "test"), None)
        return validation, test

    async def _to_domain(self, row: ModelVersionModel) -> ModelVersion:
        validation, test = await self._latest_metrics(row.id)
        return row.to_entity(validation_metrics=validation, test_metrics=test)

    async def create_training_run(self, run: TrainingRun) -> TrainingRun:
        row = TrainingRunModel(
            id=run.id,
            model_name=run.model_name,
            status=ModelLifecycleState.CREATED.value,
            random_seed=run.config.random_seed,
            feature_refs=list(run.config.feature_refs),
            dataset_start=run.config.dataset_start,
            dataset_end=run.config.dataset_end,
            train_split=run.config.train_split,
            validation_split=run.config.validation_split,
            test_split=run.config.test_split,
            hyperparameters=run.config.hyperparameters,
            library_versions=run.config.library_versions,
            started_at=run.started_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise ModelRegistryError(f"failed to create training run: {exc}") from exc
        return row.to_entity(run.config)

    async def complete_training_run(self, run_id: uuid.UUID, model_version_id: uuid.UUID) -> TrainingRun:
        row = await self._session.get(TrainingRunModel, run_id)
        if row is None:
            raise ModelRegistryError(f"training run not found: {run_id}")
        row.status = ModelLifecycleState.TRAINED.value
        row.model_version_id = model_version_id
        row.completed_at = datetime.now(UTC)
        await self._session.flush()
        return row.to_entity(
            TrainingConfig(
                random_seed=row.random_seed,
                feature_refs=tuple(row.feature_refs),
                dataset_start=row.dataset_start,
                dataset_end=row.dataset_end,
                train_split=row.train_split,
                validation_split=row.validation_split,
                test_split=row.test_split,
                hyperparameters=dict(row.hyperparameters),
                library_versions=dict(row.library_versions),
            )
        )

    async def fail_training_run(self, run_id: uuid.UUID, error_message: str) -> TrainingRun:
        row = await self._session.get(TrainingRunModel, run_id)
        if row is None:
            raise ModelRegistryError(f"training run not found: {run_id}")
        row.status = ModelLifecycleState.FAILED.value
        row.error_message = error_message[:2000]
        row.completed_at = datetime.now(UTC)
        await self._session.flush()
        return row.to_entity(
            TrainingConfig(
                random_seed=row.random_seed,
                feature_refs=tuple(row.feature_refs),
                dataset_start=row.dataset_start,
                dataset_end=row.dataset_end,
                train_split=row.train_split,
                validation_split=row.validation_split,
                test_split=row.test_split,
                hyperparameters=dict(row.hyperparameters),
                library_versions=dict(row.library_versions),
            )
        )

    async def reserve_version(self, model_name: str) -> int:
        try:
            result = await self._session.execute(
                text(
                    "INSERT INTO model_version_counters (model_name, next_version) "
                    "VALUES (:model_name, 2) "
                    "ON CONFLICT (model_name) DO UPDATE "
                    "SET next_version = model_version_counters.next_version + 1 "
                    "RETURNING next_version - 1"
                ),
                {"model_name": model_name},
            )
            return int(result.scalar_one())
        except Exception as exc:
            raise ModelRegistryError(f"failed to reserve model version: {exc}") from exc

    async def register_version(
        self,
        *,
        model_name: str,
        version: int,
        artifact_uri: str,
        training_run_id: uuid.UUID,
        feature_refs: tuple[str, ...],
        config: TrainingConfig,
    ) -> ModelVersion:
        try:
            row = ModelVersionModel(
                model_name=model_name,
                version=version,
                stage=ModelLifecycleState.TRAINED.value,
                artifact_uri=artifact_uri,
                training_run_id=training_run_id,
                feature_refs=list(feature_refs),
            )
            self._session.add(row)
            await self._session.flush()
        except Exception as exc:
            raise ModelRegistryError(f"failed to register model version: {exc}") from exc

        _logger.info(
            "model_version_registered",
            extra={
                "channel": "application",
                "model_name": model_name,
                "version": version,
                "version_id": str(row.id),
            },
        )
        return await self._to_domain(row)

    async def record_evaluation(
        self, version_id: uuid.UUID, metrics: EvaluationMetrics
    ) -> ModelVersion:
        version_row = await self._session.get(ModelVersionModel, version_id)
        if version_row is None:
            raise ModelRegistryError(f"model version not found: {version_id}")

        row = ModelEvaluationModel(
            model_version_id=version_id,
            split=metrics.split,
            accuracy=metrics.accuracy,
            precision=metrics.precision,
            recall=metrics.recall,
            f1_score=metrics.f1_score,
            sample_count=metrics.sample_count,
            extra_metrics=dict(metrics.extra_metrics),
            evaluated_at=metrics.evaluated_at or datetime.now(UTC),
        )
        self._session.add(row)

        if metrics.split == "test" and version_row.stage == ModelLifecycleState.TRAINED.value:
            version_row.stage = ModelLifecycleState.VALIDATED.value

        await self._session.flush()
        return await self._to_domain(version_row)

    async def get_version(self, version_id: uuid.UUID) -> ModelVersion | None:
        row = await self._session.get(ModelVersionModel, version_id)
        if row is None:
            return None
        return await self._to_domain(row)

    async def get_production_version(self, model_name: str) -> ModelVersion | None:
        result = await self._session.execute(
            select(ModelVersionModel).where(
                ModelVersionModel.model_name == model_name,
                ModelVersionModel.stage == ModelLifecycleState.PRODUCTION.value,
            )
        )
        row = result.scalar_one_or_none()
        return await self._to_domain(row) if row is not None else None

    async def list_versions(
        self, model_name: str, *, stage: ModelLifecycleState | None = None
    ) -> list[ModelVersion]:
        statement = select(ModelVersionModel).where(ModelVersionModel.model_name == model_name)
        if stage is not None:
            statement = statement.where(ModelVersionModel.stage == stage.value)
        statement = statement.order_by(ModelVersionModel.version.desc())
        result = await self._session.execute(statement)
        return [await self._to_domain(row) for row in result.scalars().all()]

    async def promote_version(self, version_id: uuid.UUID) -> ModelVersion:
        row = await self._session.get(ModelVersionModel, version_id)
        if row is None:
            raise ModelRegistryError(f"model version not found: {version_id}")

        current_stage = ModelLifecycleState(row.stage)
        if current_stage not in (ModelLifecycleState.VALIDATED, ModelLifecycleState.STAGED):
            raise ModelStateError(
                f"cannot promote model version in stage {current_stage.value!r}; "
                f"must be 'validated' or 'staged'",
                context={"version_id": str(version_id), "current_stage": current_stage.value},
            )

        now = datetime.now(UTC)
        current_production = await self.get_production_version(row.model_name)
        if current_production is not None and current_production.id != version_id:
            prior_row = await self._session.get(ModelVersionModel, current_production.id)
            if prior_row is not None:
                prior_row.stage = ModelLifecycleState.ARCHIVED.value
                prior_row.archived_at = now
                prior_row.was_production = True

        row.stage = ModelLifecycleState.PRODUCTION.value
        row.promoted_at = now
        await self._session.flush()

        _logger.info(
            "model_version_promoted",
            extra={
                "channel": "application",
                "version_id": str(version_id),
                "model_name": row.model_name,
            },
        )
        return await self._to_domain(row)

    async def rollback_production(self, model_name: str) -> ModelVersion:
        current = await self.get_production_version(model_name)
        if current is None:
            raise ModelStateError(
                f"model {model_name!r} has no current production version to roll back from"
            )

        result = await self._session.execute(
            select(ModelVersionModel)
            .where(
                ModelVersionModel.model_name == model_name,
                ModelVersionModel.was_production.is_(True),
                ModelVersionModel.stage == ModelLifecycleState.ARCHIVED.value,
                ModelVersionModel.id != current.id,
            )
            .order_by(ModelVersionModel.archived_at.desc())
            .limit(1)
        )
        prior_row = result.scalar_one_or_none()
        if prior_row is None:
            raise ModelStateError(
                f"model {model_name!r} has no prior production version to roll back to"
            )

        now = datetime.now(UTC)
        current_row = await self._session.get(ModelVersionModel, current.id)
        assert current_row is not None
        current_row.stage = ModelLifecycleState.ARCHIVED.value
        current_row.archived_at = now
        current_row.was_production = True

        prior_row.stage = ModelLifecycleState.PRODUCTION.value
        prior_row.promoted_at = now
        await self._session.flush()

        _logger.warning(
            "model_version_rolled_back",
            extra={
                "channel": "application",
                "model_name": model_name,
                "rolled_back_from": str(current.id),
                "rolled_back_to": str(prior_row.id),
            },
        )
        return await self._to_domain(prior_row)

    async def archive_version(self, version_id: uuid.UUID) -> ModelVersion:
        row = await self._session.get(ModelVersionModel, version_id)
        if row is None:
            raise ModelRegistryError(f"model version not found: {version_id}")
        if row.stage == ModelLifecycleState.PRODUCTION.value:
            raise ModelStateError(
                "cannot archive the current production version directly; "
                "promote a replacement or call rollback_production() first",
                context={"version_id": str(version_id)},
            )
        row.stage = ModelLifecycleState.ARCHIVED.value
        row.archived_at = datetime.now(UTC)
        await self._session.flush()
        return await self._to_domain(row)


__all__ = [
    "ModelEvaluationModel",
    "ModelVersionModel",
    "ModelVersionCounterModel",
    "PostgresModelRegistry",
    "TrainingRunModel",
]
