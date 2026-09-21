"""Holdout validation and metric computation for trained models.

:class:`ModelEvaluator` computes
``core.domain.entities.model_version.EvaluationMetrics`` for a fitted model
against a held-out split, and :func:`meets_promotion_criteria` compares those
metrics against ``config.modules.training.TrainingSettings``'s configured
thresholds -- the single source of truth
``mlops/promotion_policy.py`` calls into, so a promotion decision is never
made two different ways in two different places.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from config.modules.training import TrainingSettings
from core.domain.entities.model_version import EvaluationMetrics
from models.model_definitions.lstm_price_model import BaselineDirectionModel


class ModelEvaluator:
    """Computes :class:`EvaluationMetrics` for a fitted
    :class:`~models.model_definitions.lstm_price_model.BaselineDirectionModel`
    against one dataset split."""

    def evaluate(
        self,
        model: BaselineDirectionModel,
        features: pd.DataFrame,
        labels: pd.Series,
        *,
        split: str,
    ) -> EvaluationMetrics:
        predictions = model.predict(features)
        truth = labels.to_numpy()

        return EvaluationMetrics(
            split=split,
            accuracy=float(accuracy_score(truth, predictions)),
            precision=float(precision_score(truth, predictions, zero_division=0)),
            recall=float(recall_score(truth, predictions, zero_division=0)),
            f1_score=float(f1_score(truth, predictions, zero_division=0)),
            sample_count=int(len(truth)),
            extra_metrics={"positive_rate": float(np.mean(truth))},
            evaluated_at=datetime.now(UTC),
        )


def meets_promotion_criteria(metrics: EvaluationMetrics, settings: TrainingSettings) -> bool:
    """Whether ``metrics`` (expected to be the ``"test"``-split metrics)
    clears every configured promotion threshold.

    Deliberately a plain function (not a method on :class:`ModelEvaluator`)
    since it depends only on already-computed metrics plus configuration --
    no model or dataset access needed -- keeping pure decision logic separate
    from the class doing the (stateful, I/O-adjacent) computation that
    produces its inputs.
    """
    return (
        metrics.accuracy >= settings.min_promotion_accuracy
        and metrics.f1_score >= settings.min_promotion_f1
    )


__all__ = ["ModelEvaluator", "meets_promotion_criteria"]
