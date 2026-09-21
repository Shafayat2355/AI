"""Model training settings, backing ``training/trainer.py``,
``training/validation.py``, ``mlops/promotion_policy.py``, and
``models/artifact_store.py``.

Environment variables use the ``TRAINING_`` prefix. Deliberately a module
distinct from ``config.modules.ai_models.AIModelSettings`` -- ``AIModelSettings``
governs registry *lookup*/inference-serving concerns (which stage to resolve,
inference timeout, canary routing), while this module governs the training
*run* itself (reproducibility seed, dataset split, promotion thresholds,
artifact storage), matching this repo's one-settings-module-per-concern
convention.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from config.base import ModuleBaseSettings, module_settings_config


class TrainingSettings(ModuleBaseSettings):
    """Reproducibility, dataset, and promotion configuration for training runs."""

    model_config = module_settings_config(env_prefix="TRAINING_")

    random_seed: int = Field(
        default=42,
        description="Seed applied to every source of randomness in a training "
        "run (dataset shuffling, model fitting) for reproducibility.",
    )
    train_split: float = Field(
        default=0.70, description="Fraction of the dataset used for training.", gt=0.0, lt=1.0
    )
    validation_split: float = Field(
        default=0.15, description="Fraction of the dataset used for validation.", gt=0.0, lt=1.0
    )
    test_split: float = Field(
        default=0.15,
        description="Fraction of the dataset held out for final testing.",
        gt=0.0,
        lt=1.0,
    )
    label_horizon_bars: int = Field(
        default=1,
        description="How many bars ahead the training label looks "
        "(1 = predict the direction of the next bar).",
        ge=1,
    )
    artifact_store_backend: str = Field(
        default="local",
        description="Model artifact storage backend. Only 'local' (filesystem) "
        "is implemented; 's3' is reserved so ModelArtifactStorePort implementations "
        "can be added later without an interface change.",
    )
    artifact_store_dir: str = Field(
        default="/var/lib/ai-trading-platform/model_artifacts",
        description="Filesystem root for the local model artifact store backend.",
    )
    min_promotion_accuracy: float = Field(
        default=0.52,
        description="Minimum test-set accuracy a candidate model must reach to "
        "be eligible for promotion (mlops/promotion_policy.py). Deliberately just "
        "above the 0.50 no-skill baseline for a binary direction-prediction problem "
        "-- see docs/PHASE12_ML_TRAINING_MODEL_MANAGEMENT.md 'Baseline model' for why "
        "this is not, and is not claimed to be, a production trading threshold.",
        ge=0.0,
        le=1.0,
    )
    min_promotion_f1: float = Field(
        default=0.50,
        description="Minimum test-set F1 score required for promotion.",
        ge=0.0,
        le=1.0,
    )
    n_estimators: int = Field(
        default=200,
        description="Baseline model hyperparameter: number of boosting stages.",
        ge=1,
    )
    max_depth: int = Field(
        default=3,
        description="Baseline model hyperparameter: max tree depth per estimator.",
        ge=1,
    )
    learning_rate: float = Field(
        default=0.05,
        description="Baseline model hyperparameter: gradient boosting learning rate.",
        gt=0.0,
    )
    scheduled_training_lookback_bars: int = Field(
        default=24 * 90,
        description="Bars of history requested when a scheduled training run "
        "builds its dataset (nightly_training_job.py).",
        ge=100,
    )

    @model_validator(mode="after")
    def _validate_splits_sum_to_one(self) -> TrainingSettings:
        total = self.train_split + self.validation_split + self.test_split
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"train_split + validation_split + test_split must sum to 1.0, got {total}"
            )
        return self


__all__ = ["TrainingSettings"]
