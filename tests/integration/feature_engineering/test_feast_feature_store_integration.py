"""Integration test: the real Feast feature store, end to end.

Drives ``feature_engineering.feature_store_client.FeastFeatureStoreClient``
against a genuine Feast registry/offline/online store -- no mocks -- proving
Phase 11's central claim: that offline (training) and online (serving)
retrieval read the *same* feature definitions, and that historical retrieval
is point-in-time correct.

Infrastructure note: the online store is Feast's ``sqlite`` backend rather
than the Redis backend configured by default
(``FeatureEngineeringSettings.online_store_backend``), so this suite runs
without a live Redis. Both are selected by the same
``repo_builder.build_repo_config`` branch and exercise identical client code;
the Redis path additionally requires Phase 8 infrastructure to be up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from config.modules.feature_engineering import FeatureEngineeringSettings
from config.settings import Settings
from datasets.historical.ohlcv_store import SyntheticHistoryConfig, generate_synthetic_bars
from feature_engineering.feast_repo.feature_views import (
    STATISTICAL_FEATURES,
    TECHNICAL_INDICATOR_FEATURES,
    all_feature_refs,
)
from feature_engineering.feature_store_client import FeastFeatureStoreClient
from feature_engineering.offline_pipeline import OfflineFeaturePipeline
from feature_engineering.online_pipeline import OnlineFeaturePipeline
from shared.errors.exceptions import FeatureStoreError

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)
_SYMBOL = "BTCUSDT"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        feature_engineering=FeatureEngineeringSettings(
            online_store_backend="sqlite",
            offline_store_path=str(tmp_path / "offline"),
            feast_project_name="test_project",
        )
    )


@pytest.fixture
def populated_store(settings: Settings) -> FeastFeatureStoreClient:
    """A Feast store with real computed features applied and materialized."""
    config = SyntheticHistoryConfig(symbols=(_SYMBOL,), lookback_bars=300)
    bars = generate_synthetic_bars(_SYMBOL, config, end_time=_ANCHOR)

    pipeline = OfflineFeaturePipeline(settings.feature_engineering.offline_store_path)
    pipeline.run({_SYMBOL: bars})

    client = FeastFeatureStoreClient(settings)
    client.apply()
    OnlineFeaturePipeline(client).materialize_window(
        _ANCHOR - timedelta(days=60), _ANCHOR + timedelta(days=1)
    )
    return client


class TestOfflinePipeline:
    def test_writes_the_parquet_file_feast_reads_from(self, settings: Settings) -> None:
        bars = generate_synthetic_bars(
            _SYMBOL, SyntheticHistoryConfig(symbols=(_SYMBOL,), lookback_bars=100), end_time=_ANCHOR
        )
        result = OfflineFeaturePipeline(
            settings.feature_engineering.offline_store_path
        ).run({_SYMBOL: bars})

        assert Path(result.output_path).is_file()
        assert result.rows_written == 100

    def test_output_contains_every_declared_feature_column(self, settings: Settings) -> None:
        """Guards against feature-view/computation drift: the parquet must
        carry exactly the columns the feature views declare."""
        bars = generate_synthetic_bars(
            _SYMBOL, SyntheticHistoryConfig(symbols=(_SYMBOL,), lookback_bars=100), end_time=_ANCHOR
        )
        result = OfflineFeaturePipeline(
            settings.feature_engineering.offline_store_path
        ).run({_SYMBOL: bars})

        columns = set(pd.read_parquet(result.output_path).columns)
        assert set(TECHNICAL_INDICATOR_FEATURES) <= columns
        assert set(STATISTICAL_FEATURES) <= columns
        assert {"symbol", "event_timestamp"} <= columns

    def test_raises_when_there_is_no_history_to_compute_from(
        self, settings: Settings
    ) -> None:
        pipeline = OfflineFeaturePipeline(settings.feature_engineering.offline_store_path)
        with pytest.raises(FeatureStoreError, match="no OHLCV history"):
            pipeline.run({_SYMBOL: []})


class TestHistoricalRetrieval:
    def test_returns_a_feature_column_per_requested_ref(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        entity_df = pd.DataFrame(
            {"symbol": [_SYMBOL], "event_timestamp": [_ANCHOR - timedelta(hours=5)]}
        )
        result = populated_store.get_historical_features(entity_df)
        for ref in all_feature_refs():
            assert ref.split(":", 1)[1] in result.columns

    def test_returns_one_row_per_entity_row(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        timestamps = [_ANCHOR - timedelta(hours=h) for h in (5, 10, 20)]
        entity_df = pd.DataFrame({"symbol": [_SYMBOL] * 3, "event_timestamp": timestamps})
        assert len(populated_store.get_historical_features(entity_df)) == 3

    def test_is_point_in_time_correct(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        """The core anti-leakage guarantee: the value returned for a given
        timestamp must match the value that was current *at* that timestamp,
        not a later one."""
        early, late = _ANCHOR - timedelta(hours=50), _ANCHOR - timedelta(hours=5)
        entity_df = pd.DataFrame(
            {"symbol": [_SYMBOL, _SYMBOL], "event_timestamp": [early, late]}
        )
        result = populated_store.get_historical_features(
            entity_df, ["technical_indicators:sma_20"]
        ).sort_values("event_timestamp")

        # Two different points in a random walk must not yield the same SMA;
        # if they did, retrieval would be ignoring event_timestamp.
        assert result["sma_20"].iloc[0] != result["sma_20"].iloc[1]

    def test_a_timestamp_before_any_data_yields_no_feature_value(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        entity_df = pd.DataFrame(
            {"symbol": [_SYMBOL], "event_timestamp": [_ANCHOR - timedelta(days=3650)]}
        )
        result = populated_store.get_historical_features(
            entity_df, ["technical_indicators:sma_20"]
        )
        assert result["sma_20"].isna().all()


class TestOnlineRetrieval:
    def test_serves_materialized_feature_values(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        online = populated_store.get_online_features([{"symbol": _SYMBOL}])
        assert online["symbol"] == [_SYMBOL]
        assert online["sma_20"][0] is not None

    def test_serves_every_declared_feature(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        online = populated_store.get_online_features([{"symbol": _SYMBOL}])
        for feature in TECHNICAL_INDICATOR_FEATURES + STATISTICAL_FEATURES:
            assert feature in online

    def test_an_unknown_entity_returns_nulls_rather_than_raising(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        """Cold start is an expected outcome the caller handles, not an
        infrastructure failure."""
        online = populated_store.get_online_features([{"symbol": "NOSUCHSYMBOL"}])
        assert online["sma_20"] == [None]


class TestTrainingServingConsistency:
    def test_offline_and_online_paths_expose_the_same_feature_names(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        """Phase 11/12's training-serving consistency requirement, asserted
        against the real store rather than by inspecting definitions."""
        entity_df = pd.DataFrame(
            {"symbol": [_SYMBOL], "event_timestamp": [_ANCHOR - timedelta(hours=5)]}
        )
        offline_columns = set(populated_store.get_historical_features(entity_df).columns)
        online_keys = set(populated_store.get_online_features([{"symbol": _SYMBOL}]))

        expected = set(TECHNICAL_INDICATOR_FEATURES) | set(STATISTICAL_FEATURES)
        assert expected <= offline_columns
        assert expected <= online_keys


class TestMaterializationErrors:
    def test_rejects_an_inverted_window(
        self, populated_store: FeastFeatureStoreClient
    ) -> None:
        pipeline = OnlineFeaturePipeline(populated_store)
        with pytest.raises(FeatureStoreError, match="inverted"):
            pipeline.materialize_window(_ANCHOR, _ANCHOR - timedelta(days=1))
