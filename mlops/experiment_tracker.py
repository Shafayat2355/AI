"""Records experiment parameters, metrics, and lineage for each training run.

Deliberately a thin, read-oriented wrapper over the tables
``models/registry_client.py`` already writes (``training_runs``,
``model_versions``, ``model_evaluations``) rather than a second, parallel
place experiment metadata is written to -- Phase 12's reproducibility
requirement (seed, feature refs, dataset window, hyperparameters, library
versions) is satisfied entirely by ``TrainingRunModel``'s columns. This module
exists so a caller (a future dashboard, or an operator debugging a run) has
one place to ask "what happened during training run X and what did it
produce" without composing three raw queries by hand each time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.registry_client import ModelEvaluationModel, ModelVersionModel, TrainingRunModel


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    """Everything recorded about one training run and the model version (if
    any) it produced."""

    training_run: dict[str, Any]
    model_version: dict[str, Any] | None
    evaluations: list[dict[str, Any]]


class ExperimentTracker:
    """Read access to training-run lineage, backed by the same session/tables
    ``models.registry_client.PostgresModelRegistry`` writes to."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_report(self, training_run_id: UUID) -> ExperimentReport | None:
        run = await self._session.get(TrainingRunModel, training_run_id)
        if run is None:
            return None

        run_dict = {
            "id": str(run.id),
            "model_name": run.model_name,
            "status": run.status,
            "random_seed": run.random_seed,
            "feature_refs": run.feature_refs,
            "dataset_start": run.dataset_start.isoformat(),
            "dataset_end": run.dataset_end.isoformat(),
            "train_split": run.train_split,
            "validation_split": run.validation_split,
            "test_split": run.test_split,
            "hyperparameters": run.hyperparameters,
            "library_versions": run.library_versions,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_message": run.error_message,
        }

        version_dict: dict[str, Any] | None = None
        evaluations: list[dict[str, Any]] = []
        result = await self._session.execute(
            select(ModelVersionModel).where(ModelVersionModel.training_run_id == training_run_id)
        )
        version_row = result.scalar_one_or_none()
        if version_row is not None:
            version_dict = {
                "id": str(version_row.id),
                "model_name": version_row.model_name,
                "version": version_row.version,
                "stage": version_row.stage,
                "artifact_uri": version_row.artifact_uri,
            }
            eval_result = await self._session.execute(
                select(ModelEvaluationModel).where(
                    ModelEvaluationModel.model_version_id == version_row.id
                )
            )
            evaluations = [
                {
                    "split": row.split,
                    "accuracy": row.accuracy,
                    "precision": row.precision,
                    "recall": row.recall,
                    "f1_score": row.f1_score,
                    "sample_count": row.sample_count,
                }
                for row in eval_result.scalars().all()
            ]

        return ExperimentReport(
            training_run=run_dict, model_version=version_dict, evaluations=evaluations
        )


__all__ = ["ExperimentReport", "ExperimentTracker"]
