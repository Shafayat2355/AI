"""Model-registry domain entities: framework-free value types describing a
trained model's lifecycle, evaluation results, and the training run that
produced it.

Placed under ``core/domain`` (not ``models/``) for the same reason
``core/domain/entities/tick.py`` is: these are exactly the shapes
``core/ports/model_registry_port.py`` and
``core/ports/model_artifact_store_port.py`` need to describe in their method
signatures, and ``core`` (domain + ports) must not depend on an outer layer
like ``models/`` -- so the types those ports speak in have to live here, with
``models/registry_client.py`` (the concrete Postgres-backed adapter) mapping
its own ORM rows to and from them, exactly as
``database/repositories/ohlcv_bar_repository.py`` does for
:class:`~core.domain.entities.tick.OHLCVBar`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ModelLifecycleState(StrEnum):
    """A model version's position in the training -> promotion -> retirement
    lifecycle (Phase 12's "Model registry" requirement).

    Linear happy path: ``CREATED -> TRAINED -> VALIDATED -> STAGED ->
    PRODUCTION -> ARCHIVED``. ``FAILED`` is reachable from ``CREATED`` or
    ``TRAINED`` (training or evaluation raised). Enforcement of which
    transitions are legal lives in ``models/registry_client.py``
    (raises :class:`~shared.errors.exceptions.ModelStateError` on an illegal
    one) rather than on this enum, keeping this type a plain, portable value.
    """

    CREATED = "created"
    TRAINED = "trained"
    VALIDATED = "validated"
    STAGED = "staged"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    FAILED = "failed"


#: Legal forward transitions. ``registry_client.py`` also allows PRODUCTION ->
#: STAGED (rollback) as a special case, not modeled here since it moves
#: *backward* through the lifecycle rather than forward.
ALLOWED_TRANSITIONS: dict[ModelLifecycleState, frozenset[ModelLifecycleState]] = {
    ModelLifecycleState.CREATED: frozenset(
        {ModelLifecycleState.TRAINED, ModelLifecycleState.FAILED}
    ),
    ModelLifecycleState.TRAINED: frozenset(
        {ModelLifecycleState.VALIDATED, ModelLifecycleState.FAILED}
    ),
    ModelLifecycleState.VALIDATED: frozenset(
        {ModelLifecycleState.STAGED, ModelLifecycleState.ARCHIVED}
    ),
    ModelLifecycleState.STAGED: frozenset(
        {ModelLifecycleState.PRODUCTION, ModelLifecycleState.ARCHIVED}
    ),
    ModelLifecycleState.PRODUCTION: frozenset({ModelLifecycleState.ARCHIVED}),
    ModelLifecycleState.ARCHIVED: frozenset(),
    ModelLifecycleState.FAILED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Evaluation results for one model version against one dataset split
    (validation or test).

    A plain ``dict`` for ``extra_metrics`` (rather than a fixed field per
    metric) so ``training/validation.py`` can record problem-specific metrics
    without a schema migration -- ``accuracy``/``f1_score``/``precision``/
    ``recall`` are pulled out as first-class fields because
    :mod:`mlops.promotion_policy` and
    ``config.modules.training.TrainingSettings``'s promotion thresholds
    compare against them directly.
    """

    split: str  # "validation" | "test"
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sample_count: int
    extra_metrics: dict[str, float] = field(default_factory=dict)
    evaluated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Everything needed to reproduce a training run byte-for-byte (Phase
    12's reproducibility requirement): the seed, dataset window, feature
    refs, and model hyperparameters actually used."""

    random_seed: int
    feature_refs: tuple[str, ...]
    dataset_start: datetime
    dataset_end: datetime
    train_split: float
    validation_split: float
    test_split: float
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    library_versions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrainingRun:
    """One execution of the training pipeline: its configuration, the
    resulting model version (once known), and its outcome."""

    id: UUID
    model_name: str
    config: TrainingConfig
    started_at: datetime
    completed_at: datetime | None = None
    status: ModelLifecycleState = ModelLifecycleState.CREATED
    model_version_id: UUID | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ModelVersion:
    """One registered, versioned model artifact and its metadata.

    ``artifact_uri`` is whatever
    ``core.ports.model_artifact_store_port.ModelArtifactStorePort`` returned
    when the artifact was stored -- opaque to the registry itself, per that
    port's own docstring on keeping local-filesystem-vs-S3 an implementation
    detail.
    """

    id: UUID
    model_name: str
    version: int
    stage: ModelLifecycleState
    artifact_uri: str
    training_run_id: UUID
    feature_refs: tuple[str, ...]
    created_at: datetime
    validation_metrics: EvaluationMetrics | None = None
    test_metrics: EvaluationMetrics | None = None
    promoted_at: datetime | None = None
    archived_at: datetime | None = None


__all__ = [
    "ALLOWED_TRANSITIONS",
    "EvaluationMetrics",
    "ModelLifecycleState",
    "ModelVersion",
    "TrainingConfig",
    "TrainingRun",
]
