"""Baseline prediction model: gradient-boosted trees predicting next-bar
price direction from technical/statistical features.

The module's name (kept for compatibility with the Phase 2 scaffold; nothing
else in this codebase imports it, confirmed by search before repurposing it)
promised an LSTM. This implementation deliberately uses scikit-learn's
:class:`~sklearn.ensemble.GradientBoostingClassifier` instead, for reasons
worth being explicit about rather than silently diverging from the filename:

* The feature set this platform's Feast feature views expose
  (``feature_engineering/feast_repo/feature_views.py``) is tabular --
  per-bar indicator values, not a raw price sequence -- which is exactly the
  input shape gradient boosting is suited to; an LSTM's advantage (learning
  temporal structure directly from a sequence) does not apply when the
  sequence has already been hand-summarized into rolling-window features.
* It trains deterministically and quickly on CPU with a fixed seed, which
  Phase 12's reproducibility requirement needs and a from-scratch PyTorch
  training loop makes considerably harder to guarantee bit-for-bit.
* It keeps this baseline's only new dependency (``scikit-learn``) one already
  declared in ``requirements/training.txt`` before this phase, rather than
  adding GPU/CPU-variant wheel selection concerns for a baseline whose whole
  point (per the "Baseline model" requirement) is infrastructure validation,
  not maximizing predictive accuracy.

``training/trainer.py``, ``models/registry_client.py``, and
``inference/predictor.py`` all depend on this class's small
fit/predict/serialize interface, never on scikit-learn directly.
"""

from __future__ import annotations

import pickle
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from shared.errors.exceptions import TrainingError


class BaselineDirectionModel:
    """Predicts whether the next bar closes up (1) or not-up (0) from a row
    of technical/statistical feature values.

    Deliberately a binary classifier over "up vs. not up" rather than a
    3-way up/flat/down classifier or a return-magnitude regressor -- the
    simplest well-posed version of "does this platform's ML infrastructure
    work end to end", which is this baseline's actual purpose (see this
    module's docstring -- no claim of production trading accuracy is made or
    implied by this class).
    """

    def __init__(
        self,
        *,
        n_estimators: int = 200,
        max_depth: int = 3,
        learning_rate: float = 0.05,
        random_seed: int = 42,
    ) -> None:
        self._feature_columns: list[str] | None = None
        self._model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=random_seed,
        )

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> None:
        """Fit on ``features`` (feature columns only -- no ``symbol``/
        ``event_timestamp``/``label``) against binary ``labels``."""
        if features.empty:
            raise TrainingError("cannot fit BaselineDirectionModel on an empty feature frame")
        self._feature_columns = list(features.columns)
        self._model.fit(features.to_numpy(), labels.to_numpy())

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return the predicted class (0/1) for each row of ``features``."""
        self._ensure_fitted()
        aligned = self._align_columns(features)
        return self._model.predict(aligned.to_numpy())

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Return ``P(class=1)`` for each row of ``features`` -- what
        ``inference/predictor.py`` reports as the prediction's confidence."""
        self._ensure_fitted()
        aligned = self._align_columns(features)
        return self._model.predict_proba(aligned.to_numpy())[:, 1]

    def _align_columns(self, features: pd.DataFrame) -> pd.DataFrame:
        assert self._feature_columns is not None
        missing = [c for c in self._feature_columns if c not in features.columns]
        if missing:
            raise TrainingError(
                "inference feature payload is missing columns the model was trained on "
                "(training/serving skew)",
                context={"missing_columns": missing},
            )
        return features[self._feature_columns]

    def _ensure_fitted(self) -> None:
        if self._feature_columns is None:
            raise TrainingError("BaselineDirectionModel.predict called before fit()")

    def serialize(self) -> bytes:
        """Serialize this model (including its fitted state and feature
        column order) to bytes for ``models/artifact_store.py``."""
        self._ensure_fitted()
        return pickle.dumps(
            {"model": self._model, "feature_columns": self._feature_columns},
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    @classmethod
    def deserialize(cls, data: bytes) -> BaselineDirectionModel:
        """Reconstruct a fitted :class:`BaselineDirectionModel` from bytes
        produced by :meth:`serialize`."""
        try:
            payload: dict[str, Any] = pickle.loads(data)  # noqa: S301 - our own artifact format
        except Exception as exc:
            raise TrainingError(f"failed to deserialize model artifact: {exc}") from exc
        instance = cls.__new__(cls)
        instance._model = payload["model"]
        instance._feature_columns = payload["feature_columns"]
        return instance


__all__ = ["BaselineDirectionModel"]
