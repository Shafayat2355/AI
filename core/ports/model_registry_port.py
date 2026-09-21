"""Abstract interface for model-registry lifecycle operations.

Implemented by ``models/registry_client.py`` (backed by PostgreSQL, per Phase
12). Following ``core/ports/feature_store_port.py``/``event_publisher_port.py``'s
precedent: ``core`` and ``training/``, ``inference/``, ``mlops/`` depend on
this abstraction, never on ``models/registry_client.py``'s concrete adapter
directly. The composition root (``core/container.py``) wires the concrete
registry in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from core.domain.entities.model_version import (
    EvaluationMetrics,
    ModelLifecycleState,
    ModelVersion,
    TrainingConfig,
)


class ModelRegistryPort(ABC):
    """Contract a model-registry adapter must satisfy: register/version/
    query/promote/rollback/archive, backed by persistent metadata storage."""

    @abstractmethod
    async def reserve_version(self, model_name: str) -> int:
        """Reserve and return the next version number for ``model_name``
        without creating a row yet.

        Exists so ``training/trainer.py`` can write its artifact to a path
        keyed by the real version number *before* registering it -- the
        alternative (register with a placeholder URI, re-save, then update
        the row) leaves the registry pointing at a stale path if any step
        between the two writes fails.
        """

    @abstractmethod
    async def register_version(
        self,
        *,
        model_name: str,
        version: int,
        artifact_uri: str,
        training_run_id: UUID,
        feature_refs: tuple[str, ...],
        config: TrainingConfig,
    ) -> ModelVersion:
        """Register an already-stored model artifact as ``version`` of
        ``model_name``, in :attr:`~core.domain.entities.model_version.ModelLifecycleState.TRAINED`
        state. ``version`` comes from a prior :meth:`reserve_version` call.

        Must raise :class:`~shared.errors.exceptions.ModelRegistryError` on a
        persistence failure, including a duplicate ``(model_name, version)``.
        """

    @abstractmethod
    async def record_evaluation(
        self, version_id: UUID, metrics: EvaluationMetrics
    ) -> ModelVersion:
        """Attach evaluation ``metrics`` to the version identified by
        ``version_id`` and, if ``metrics.split == "test"`` and the version was
        in ``TRAINED``, advance it to
        :attr:`~core.domain.entities.model_version.ModelLifecycleState.VALIDATED`.

        Does **not** decide whether the model qualifies for promotion --
        that decision belongs to ``mlops/promotion_policy.py``, which reads
        these recorded metrics back and compares them against
        ``config.modules.training.TrainingSettings``'s thresholds.
        """

    @abstractmethod
    async def get_version(self, version_id: UUID) -> ModelVersion | None:
        """Return the model version identified by ``version_id``, or ``None``
        if it does not exist."""

    @abstractmethod
    async def get_production_version(self, model_name: str) -> ModelVersion | None:
        """Return the version of ``model_name`` currently in
        :attr:`~core.domain.entities.model_version.ModelLifecycleState.PRODUCTION`
        state, or ``None`` if no version has ever been promoted. This is what
        ``inference/model_loader.py`` calls when the caller does not pin a
        specific version.
        """

    @abstractmethod
    async def list_versions(
        self, model_name: str, *, stage: ModelLifecycleState | None = None
    ) -> list[ModelVersion]:
        """List every version of ``model_name``, newest first, optionally
        filtered to a single ``stage``."""

    @abstractmethod
    async def promote_version(self, version_id: UUID) -> ModelVersion:
        """Promote the version identified by ``version_id`` to
        :attr:`~core.domain.entities.model_version.ModelLifecycleState.PRODUCTION`,
        first moving it through ``STAGED`` if it is not already there, and
        demoting any currently-``PRODUCTION`` version of the same
        ``model_name`` to ``ARCHIVED`` -- exactly one version of a given
        model is ``PRODUCTION`` at a time.

        Must raise :class:`~shared.errors.exceptions.ModelStateError` if
        ``version_id``'s current stage does not allow promotion (see
        :data:`~core.domain.entities.model_version.ALLOWED_TRANSITIONS`).
        """

    @abstractmethod
    async def rollback_production(self, model_name: str) -> ModelVersion:
        """Demote the current ``PRODUCTION`` version of ``model_name`` to
        ``ARCHIVED`` and promote the most recently ``ARCHIVED`` version that
        was previously ``PRODUCTION`` (i.e. the prior champion) back to
        ``PRODUCTION``.

        Must raise :class:`~shared.errors.exceptions.ModelStateError` if
        ``model_name`` has no current production version, or no prior
        production version exists to roll back to.
        """

    @abstractmethod
    async def archive_version(self, version_id: UUID) -> ModelVersion:
        """Move the version identified by ``version_id`` to ``ARCHIVED``.

        Must raise :class:`~shared.errors.exceptions.ModelStateError` if
        ``version_id`` is the current ``PRODUCTION`` version -- use
        :meth:`rollback_production` or :meth:`promote_version` (of a
        replacement) instead, so a model is never left with no production
        version implicitly.
        """


__all__ = ["ModelRegistryPort"]
