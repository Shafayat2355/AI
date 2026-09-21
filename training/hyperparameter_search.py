"""Hyperparameter search/tuning logic invoked by the trainer.

A small, deterministic grid search over
:class:`~models.model_definitions.lstm_price_model.BaselineDirectionModel`'s
hyperparameters, selected by validation-split accuracy. Deliberately a plain
exhaustive grid (not Optuna/random search, despite ``optuna`` already being a
declared dependency in ``requirements/training.txt``) -- the baseline model's
hyperparameter space is small (three knobs) and this keeps the search
reproducible from ``config.modules.training.TrainingSettings.random_seed``
alone, without needing to also pin an Optuna sampler's own RNG state. A future
model with a larger search space is a legitimate reason to introduce Optuna
here without changing :func:`search_hyperparameters`'s signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import pandas as pd

from models.model_definitions.lstm_price_model import BaselineDirectionModel
from training.validation import ModelEvaluator


@dataclass(frozen=True, slots=True)
class HyperparameterGrid:
    """Candidate values for each of :class:`BaselineDirectionModel`'s
    hyperparameters. Defaults to a single point (the configured defaults),
    so a caller that does not want a search still goes through this same
    code path with exactly one candidate evaluated.
    """

    n_estimators: tuple[int, ...] = (200,)
    max_depth: tuple[int, ...] = (3,)
    learning_rate: tuple[float, ...] = (0.05,)


@dataclass(frozen=True, slots=True)
class SearchResult:
    best_params: dict[str, int | float]
    best_validation_accuracy: float
    all_results: list[dict[str, float]] = field(default_factory=list)


def search_hyperparameters(
    train_features: pd.DataFrame,
    train_labels: pd.Series,
    validation_features: pd.DataFrame,
    validation_labels: pd.Series,
    *,
    grid: HyperparameterGrid,
    random_seed: int,
) -> SearchResult:
    """Fit one model per point in ``grid``'s Cartesian product on
    ``(train_features, train_labels)``, evaluate each on
    ``(validation_features, validation_labels)``, and return the
    highest-validation-accuracy configuration.

    Ties are broken by grid order (first candidate wins), keeping this
    deterministic for a fixed ``grid``/``random_seed``.
    """
    evaluator = ModelEvaluator()
    all_results: list[dict[str, float]] = []
    best_params: dict[str, int | float] | None = None
    best_accuracy = -1.0

    for n_estimators, max_depth, learning_rate in product(
        grid.n_estimators, grid.max_depth, grid.learning_rate
    ):
        model = BaselineDirectionModel(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_seed=random_seed,
        )
        model.fit(train_features, train_labels)
        metrics = evaluator.evaluate(
            model, validation_features, validation_labels, split="validation"
        )

        candidate = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
        }
        all_results.append({**candidate, "validation_accuracy": metrics.accuracy})

        if metrics.accuracy > best_accuracy:
            best_accuracy = metrics.accuracy
            best_params = candidate

    assert best_params is not None  # grid always has >= 1 point
    return SearchResult(
        best_params=best_params, best_validation_accuracy=best_accuracy, all_results=all_results
    )


__all__ = ["HyperparameterGrid", "SearchResult", "search_hyperparameters"]
