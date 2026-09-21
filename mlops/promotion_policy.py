"""Encodes the criteria a candidate model must meet to be promoted to champion.

:func:`evaluate_candidate_model` is the integration point
``scheduler/jobs/model_evaluation_job.py`` already calls. The actual
threshold check is ``training.validation.meets_promotion_criteria`` -- kept
there (not duplicated here) since it is also needed at training time
(``training/trainer.py`` reports ``promotable`` on every
:class:`~training.trainer.TrainingResult`) and a promotion decision must be
made the same way in both places.
"""

from __future__ import annotations

from config.settings import Settings
from core.domain.entities.model_version import ModelLifecycleState, ModelVersion
from core.ports.model_registry_port import ModelRegistryPort
from shared.errors.exceptions import ModelValidationError
from shared.logging.logger import get_logger
from training.validation import meets_promotion_criteria

_logger = get_logger("mlops.promotion_policy")


class PromotionPolicy:
    """Decides whether a specific candidate model version qualifies for
    promotion, and (if so) promotes it -- against an injected
    :class:`~core.ports.model_registry_port.ModelRegistryPort`, no direct
    Postgres dependency."""

    def __init__(self, model_registry: ModelRegistryPort, settings: Settings) -> None:
        self._model_registry = model_registry
        self._settings = settings

    async def find_candidate(self, model_name: str) -> ModelVersion | None:
        """Return the newest ``VALIDATED`` (not yet staged/promoted) version
        of ``model_name``, or ``None`` if there is nothing awaiting a
        promotion decision."""
        candidates = await self._model_registry.list_versions(
            model_name, stage=ModelLifecycleState.VALIDATED
        )
        return candidates[0] if candidates else None

    def qualifies(self, candidate: ModelVersion) -> bool:
        """Whether ``candidate`` clears the configured promotion thresholds,
        based on its recorded test-split metrics.

        Raises :class:`~shared.errors.exceptions.ModelValidationError` if the
        candidate has no recorded test metrics at all -- a version that has
        never been evaluated is a defect (Phase 12's evaluation step should
        always have recorded one before reaching ``VALIDATED``), not a
        legitimate "does not qualify" outcome.
        """
        if candidate.test_metrics is None:
            raise ModelValidationError(
                f"model version {candidate.id} has no recorded test metrics",
                context={"model_name": candidate.model_name, "version": candidate.version},
            )
        return meets_promotion_criteria(candidate.test_metrics, self._settings.training)

    async def evaluate_and_promote(self, model_name: str) -> ModelVersion | None:
        """Find the current candidate for ``model_name``, and promote it if
        it qualifies. Returns the (now-promoted) version, or ``None`` if
        there was no candidate or it did not qualify."""
        candidate = await self.find_candidate(model_name)
        if candidate is None:
            _logger.info(
                "no_promotion_candidate",
                extra={"channel": "application", "model_name": model_name},
            )
            return None

        if not self.qualifies(candidate):
            _logger.info(
                "promotion_candidate_rejected",
                extra={
                    "channel": "application",
                    "model_name": model_name,
                    "version": candidate.version,
                    "test_accuracy": (
                        candidate.test_metrics.accuracy if candidate.test_metrics else None
                    ),
                    "test_f1": (
                        candidate.test_metrics.f1_score if candidate.test_metrics else None
                    ),
                },
            )
            return None

        promoted = await self._model_registry.promote_version(candidate.id)
        _logger.info(
            "promotion_candidate_promoted",
            extra={"channel": "application", "model_name": model_name, "version": promoted.version},
        )
        return promoted


async def evaluate_candidate_model(*, model_name: str | None = None) -> dict[str, object]:
    """Integration point called by ``scheduler.jobs.model_evaluation_job``.

    Resolves dependencies from the process
    :class:`~core.container.Container` (same convention as
    ``training.trainer.run_training_job``), finds the current promotion
    candidate for ``model_name`` (default:
    ``settings.ai_models.default_model_name``), and promotes it if it clears
    ``config.modules.training.TrainingSettings``'s thresholds. Publishes a
    ``model_promoted`` event on ``shared.messaging.topics.MODEL_LIFECYCLE``
    when a promotion occurs.
    """
    from config.settings import get_settings
    from core.container import get_container
    from models.registry_client import PostgresModelRegistry
    from shared.messaging.events import ModelLifecycleEvent
    from shared.messaging.topics import MODEL_LIFECYCLE

    settings = get_settings()
    resolved_model_name = model_name or settings.ai_models.default_model_name
    container = get_container()

    promoted: ModelVersion | None = None
    async for session in container.db.session():
        registry = PostgresModelRegistry(session)
        policy = PromotionPolicy(registry, settings)
        promoted = await policy.evaluate_and_promote(resolved_model_name)
        await session.commit()

    if promoted is not None:
        try:
            await container.kafka_producer.publish(
                MODEL_LIFECYCLE,
                ModelLifecycleEvent(
                    source_service="mlops",
                    payload={
                        "model_name": resolved_model_name,
                        "transition": "model_promoted",
                        "model_version": promoted.version,
                    },
                ),
                key=resolved_model_name,
            )
        except Exception:  # pragma: no cover - best-effort
            _logger.warning(
                "model_lifecycle_event_publish_failed",
                extra={"channel": "application", "transition": "model_promoted"},
            )

    return {
        "model_name": resolved_model_name,
        "promoted_version": promoted.version if promoted is not None else None,
    }


__all__ = ["PromotionPolicy", "evaluate_candidate_model"]
