"""Unit tests for ``training/validation.py`` (metrics + promotion criteria),
``training/trainer.py``'s chronological split, and
``training/hyperparameter_search.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from config.modules.training import TrainingSettings
from core.domain.entities.model_version import EvaluationMetrics
from datasets.loaders.training_dataset_loader import TrainingDataset
from models.model_definitions.lstm_price_model import BaselineDirectionModel
from shared.errors.exceptions import TrainingError
from training.hyperparameter_search import HyperparameterGrid, search_hyperparameters
from training.trainer import chronological_split
from training.validation import ModelEvaluator, meets_promotion_criteria

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)


def _dataset(n: int = 100) -> TrainingDataset:
    rng = np.random.default_rng(0)
    feature_a = rng.normal(0, 1, n)
    frame = pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * n,
            "event_timestamp": [_ANCHOR + timedelta(hours=i) for i in range(n)],
            "sma_20": feature_a,
            "rsi_14": rng.normal(0, 1, n),
            "label": (feature_a > 0).astype(int),
        }
    )
    return TrainingDataset(
        frame=frame,
        feature_columns=("sma_20", "rsi_14"),
        feature_refs=("technical_indicators:sma_20", "technical_indicators:rsi_14"),
    )


def _metrics(*, accuracy: float, f1: float) -> EvaluationMetrics:
    return EvaluationMetrics(
        split="test",
        accuracy=accuracy,
        precision=0.5,
        recall=0.5,
        f1_score=f1,
        sample_count=100,
    )


class TestChronologicalSplit:
    def test_partitions_sum_to_the_whole_dataset(self) -> None:
        split = chronological_split(_dataset(100), train_split=0.7, validation_split=0.15)
        total = (
            len(split.train_features) + len(split.validation_features) + len(split.test_features)
        )
        assert total == 100

    def test_respects_the_configured_proportions(self) -> None:
        split = chronological_split(_dataset(100), train_split=0.7, validation_split=0.15)
        assert len(split.train_features) == 70
        assert len(split.validation_features) == 15
        assert len(split.test_features) == 15

    def test_splits_are_strictly_ordered_in_time_with_no_overlap(self) -> None:
        """The anti-leakage invariant: every training row must precede every
        validation row, which must precede every test row."""
        dataset = _dataset(100)
        frame = dataset.frame.sort_values("event_timestamp").reset_index(drop=True)
        split = chronological_split(dataset, train_split=0.7, validation_split=0.15)

        train_times = frame["event_timestamp"].iloc[: len(split.train_features)]
        validation_times = frame["event_timestamp"].iloc[
            len(split.train_features) : len(split.train_features) + len(split.validation_features)
        ]
        test_times = frame["event_timestamp"].iloc[
            len(split.train_features) + len(split.validation_features) :
        ]
        assert train_times.max() < validation_times.min()
        assert validation_times.max() < test_times.min()

    def test_excludes_non_feature_columns_from_the_feature_frames(self) -> None:
        split = chronological_split(_dataset(100), train_split=0.7, validation_split=0.15)
        assert list(split.train_features.columns) == ["sma_20", "rsi_14"]

    def test_labels_align_row_for_row_with_features(self) -> None:
        split = chronological_split(_dataset(100), train_split=0.7, validation_split=0.15)
        assert len(split.train_features) == len(split.train_labels)
        assert len(split.test_features) == len(split.test_labels)

    def test_rejects_a_dataset_too_small_to_split(self) -> None:
        with pytest.raises(TrainingError, match="too small"):
            chronological_split(_dataset(3), train_split=0.7, validation_split=0.15)


class TestModelEvaluator:
    def _fitted(self) -> tuple[BaselineDirectionModel, pd.DataFrame, pd.Series]:
        dataset = _dataset(200)
        features = dataset.frame[list(dataset.feature_columns)]
        labels = dataset.frame["label"]
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        return model, features, labels

    def test_reports_metrics_within_valid_ranges(self) -> None:
        model, features, labels = self._fitted()
        metrics = ModelEvaluator().evaluate(model, features, labels, split="test")
        for value in (metrics.accuracy, metrics.precision, metrics.recall, metrics.f1_score):
            assert 0.0 <= value <= 1.0

    def test_records_the_split_name_and_sample_count(self) -> None:
        model, features, labels = self._fitted()
        metrics = ModelEvaluator().evaluate(model, features, labels, split="validation")
        assert metrics.split == "validation"
        assert metrics.sample_count == len(labels)

    def test_stamps_an_evaluation_timestamp(self) -> None:
        model, features, labels = self._fitted()
        metrics = ModelEvaluator().evaluate(model, features, labels, split="test")
        assert metrics.evaluated_at is not None
        assert metrics.evaluated_at.tzinfo is not None

    def test_records_the_class_balance_as_an_extra_metric(self) -> None:
        model, features, labels = self._fitted()
        metrics = ModelEvaluator().evaluate(model, features, labels, split="test")
        assert metrics.extra_metrics["positive_rate"] == pytest.approx(labels.mean())


class TestPromotionCriteria:
    def _settings(self) -> TrainingSettings:
        return TrainingSettings(min_promotion_accuracy=0.55, min_promotion_f1=0.50)

    def test_accepts_metrics_clearing_every_threshold(self) -> None:
        assert meets_promotion_criteria(_metrics(accuracy=0.60, f1=0.55), self._settings())

    def test_rejects_metrics_failing_accuracy(self) -> None:
        assert not meets_promotion_criteria(_metrics(accuracy=0.50, f1=0.90), self._settings())

    def test_rejects_metrics_failing_f1(self) -> None:
        assert not meets_promotion_criteria(_metrics(accuracy=0.90, f1=0.10), self._settings())

    def test_thresholds_are_inclusive_at_the_boundary(self) -> None:
        assert meets_promotion_criteria(_metrics(accuracy=0.55, f1=0.50), self._settings())


class TestHyperparameterSearch:
    def test_returns_the_best_candidate_from_the_grid(self) -> None:
        dataset = _dataset(200)
        features = dataset.frame[list(dataset.feature_columns)]
        labels = dataset.frame["label"]
        result = search_hyperparameters(
            features.iloc[:150],
            labels.iloc[:150],
            features.iloc[150:],
            labels.iloc[150:],
            grid=HyperparameterGrid(n_estimators=(10, 50), max_depth=(2, 3)),
            random_seed=42,
        )
        assert result.best_params["n_estimators"] in (10, 50)
        assert len(result.all_results) == 4
        assert 0.0 <= result.best_validation_accuracy <= 1.0

    def test_is_deterministic_for_a_fixed_seed_and_grid(self) -> None:
        dataset = _dataset(200)
        features = dataset.frame[list(dataset.feature_columns)]
        labels = dataset.frame["label"]

        def run() -> dict[str, int | float]:
            return search_hyperparameters(
                features.iloc[:150],
                labels.iloc[:150],
                features.iloc[150:],
                labels.iloc[150:],
                grid=HyperparameterGrid(n_estimators=(10, 50)),
                random_seed=42,
            ).best_params

        assert run() == run()


class TestTrainingSettingsValidation:
    def test_rejects_splits_that_do_not_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            TrainingSettings(train_split=0.7, validation_split=0.7, test_split=0.7)

    def test_accepts_splits_summing_to_one(self) -> None:
        settings = TrainingSettings(train_split=0.8, validation_split=0.1, test_split=0.1)
        assert settings.train_split == 0.8
