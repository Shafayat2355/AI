"""Unit tests for the baseline model
(``models/model_definitions/lstm_price_model.py``) and the local artifact
store (``models/artifact_store.py``).

Covers Phase 12's "Model training", "Model serialization", "Model loading",
"Reproducibility", and "Error handling" requirements at the unit level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.artifact_store import LocalFilesystemArtifactStore
from models.model_definitions.lstm_price_model import BaselineDirectionModel
from shared.errors.exceptions import ModelRegistryError, TrainingError


@pytest.fixture
def dataset() -> tuple[pd.DataFrame, pd.Series]:
    """A small, linearly separable problem so the baseline can actually learn
    something -- these tests assert the *mechanics* work, not that the model
    has predictive power on real markets."""
    rng = np.random.default_rng(0)
    n = 200
    feature_a = rng.normal(0, 1, n)
    feature_b = rng.normal(0, 1, n)
    labels = (feature_a + feature_b > 0).astype(int)
    return pd.DataFrame({"sma_20": feature_a, "rsi_14": feature_b}), pd.Series(labels)


class TestBaselineDirectionModel:
    def test_fits_and_predicts_one_label_per_row(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        assert len(model.predict(features)) == len(features)

    def test_predictions_are_only_ever_zero_or_one(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        assert set(np.unique(model.predict(features))).issubset({0, 1})

    def test_probabilities_are_within_the_unit_interval(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        probabilities = model.predict_proba(features)
        assert ((probabilities >= 0) & (probabilities <= 1)).all()

    def test_learns_a_genuinely_separable_signal(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        """Guards against a model that silently predicts one constant class --
        which would still satisfy every shape assertion above."""
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        accuracy = (model.predict(features) == labels.to_numpy()).mean()
        assert accuracy > 0.9

    def test_is_reproducible_for_a_fixed_seed(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        first = BaselineDirectionModel(random_seed=42)
        first.fit(features, labels)
        second = BaselineDirectionModel(random_seed=42)
        second.fit(features, labels)
        np.testing.assert_array_equal(first.predict(features), second.predict(features))
        np.testing.assert_allclose(
            first.predict_proba(features), second.predict_proba(features)
        )

    def test_rejects_fitting_on_an_empty_frame(self) -> None:
        with pytest.raises(TrainingError, match="empty"):
            BaselineDirectionModel().fit(pd.DataFrame(), pd.Series(dtype=int))

    def test_rejects_predicting_before_fitting(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        with pytest.raises(TrainingError, match="before fit"):
            BaselineDirectionModel().predict(dataset[0])

    def test_rejects_a_payload_missing_a_trained_feature(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        """Training/serving skew must fail loudly, not predict on garbage."""
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        with pytest.raises(TrainingError, match="training/serving skew"):
            model.predict(features.drop(columns=["rsi_14"]))

    def test_reorders_columns_to_the_training_order(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        """A caller passing the right features in the wrong order must get the
        same answer, not a silently wrong one."""
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        reordered = features[["rsi_14", "sma_20"]]
        np.testing.assert_array_equal(model.predict(features), model.predict(reordered))


class TestSerialization:
    def test_round_trips_to_identical_predictions(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        restored = BaselineDirectionModel.deserialize(model.serialize())
        np.testing.assert_array_equal(model.predict(features), restored.predict(features))

    def test_preserves_the_trained_feature_column_order(
        self, dataset: tuple[pd.DataFrame, pd.Series]
    ) -> None:
        features, labels = dataset
        model = BaselineDirectionModel(random_seed=42)
        model.fit(features, labels)
        restored = BaselineDirectionModel.deserialize(model.serialize())
        with pytest.raises(TrainingError, match="training/serving skew"):
            restored.predict(features.drop(columns=["sma_20"]))

    def test_refuses_to_serialize_an_unfitted_model(self) -> None:
        with pytest.raises(TrainingError, match="before fit"):
            BaselineDirectionModel().serialize()

    def test_raises_a_typed_error_on_corrupt_artifact_bytes(self) -> None:
        with pytest.raises(TrainingError, match="deserialize"):
            BaselineDirectionModel.deserialize(b"not a pickle")


class TestLocalFilesystemArtifactStore:
    def test_saves_and_loads_the_exact_bytes(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        uri = store.save("my-model", 1, b"payload")
        assert store.load(uri) == b"payload"

    def test_returns_a_file_scheme_uri(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        assert store.save("my-model", 1, b"x").startswith("file://")

    def test_separates_versions_of_the_same_model(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        first = store.save("my-model", 1, b"v1")
        second = store.save("my-model", 2, b"v2")
        assert first != second
        assert store.load(first) == b"v1"
        assert store.load(second) == b"v2"

    def test_exists_reflects_save_and_delete(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        uri = store.save("my-model", 1, b"x")
        assert store.exists(uri)
        store.delete(uri)
        assert not store.exists(uri)

    def test_delete_is_idempotent(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        uri = store.save("my-model", 1, b"x")
        store.delete(uri)
        store.delete(uri)  # must not raise

    def test_loading_an_absent_artifact_raises_a_typed_error(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path))
        with pytest.raises(ModelRegistryError, match="failed to read"):
            store.load(f"file://{tmp_path}/nope/model.bin")

    def test_rejects_an_unrecognized_uri_scheme(self, tmp_path) -> None:
        """Guards the future-S3 boundary: an s3:// URI must not be silently
        treated as a local path."""
        store = LocalFilesystemArtifactStore(str(tmp_path))
        with pytest.raises(ModelRegistryError, match="unrecognized artifact URI scheme"):
            store.load("s3://bucket/model.bin")

    def test_creates_intermediate_directories_on_save(self, tmp_path) -> None:
        store = LocalFilesystemArtifactStore(str(tmp_path / "deep" / "nested"))
        assert store.exists(store.save("m", 1, b"x"))
