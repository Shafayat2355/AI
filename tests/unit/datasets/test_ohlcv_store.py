"""Unit tests for ``datasets/historical/ohlcv_store.py``'s pure parts: the
deterministic synthetic bar generator and the domain entity it produces.

The database-backed parts of ``OHLCVStore`` are covered by
``tests/integration/datasets/`` against a real SQLite engine, per this suite's
convention of not mocking out the persistence layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.domain.entities.tick import BarInterval, OHLCVBar
from datasets.historical.ohlcv_store import (
    INTERVAL_TIMEDELTA,
    SyntheticHistoryConfig,
    generate_synthetic_bars,
)

_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)


class TestOHLCVBarInvariants:
    def test_rejects_a_naive_open_time(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            OHLCVBar(
                symbol="BTCUSDT",
                interval=BarInterval.ONE_HOUR,
                open_time=datetime(2026, 1, 1),  # noqa: DTZ001 - deliberately naive
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
            )

    def test_rejects_high_below_low(self) -> None:
        with pytest.raises(ValueError, match="must be >="):
            OHLCVBar(
                symbol="BTCUSDT",
                interval=BarInterval.ONE_HOUR,
                open_time=_ANCHOR,
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("5"),
                close=Decimal("1"),
                volume=Decimal("1"),
            )

    def test_rejects_a_close_outside_the_high_low_range(self) -> None:
        with pytest.raises(ValueError, match="close"):
            OHLCVBar(
                symbol="BTCUSDT",
                interval=BarInterval.ONE_HOUR,
                open_time=_ANCHOR,
                open=Decimal("5"),
                high=Decimal("10"),
                low=Decimal("1"),
                close=Decimal("99"),
                volume=Decimal("1"),
            )

    def test_rejects_negative_volume(self) -> None:
        with pytest.raises(ValueError, match="volume"):
            OHLCVBar(
                symbol="BTCUSDT",
                interval=BarInterval.ONE_HOUR,
                open_time=_ANCHOR,
                open=Decimal("5"),
                high=Decimal("10"),
                low=Decimal("1"),
                close=Decimal("5"),
                volume=Decimal("-1"),
            )

    def test_rejects_an_empty_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol"):
            OHLCVBar(
                symbol="",
                interval=BarInterval.ONE_HOUR,
                open_time=_ANCHOR,
                open=Decimal("5"),
                high=Decimal("10"),
                low=Decimal("1"),
                close=Decimal("5"),
                volume=Decimal("1"),
            )


class TestGenerateSyntheticBars:
    """Phase 12's reproducibility requirement starts here -- if the *data* is
    not reproducible, nothing downstream of it can be."""

    def test_is_reproducible_for_the_same_seed_and_symbol(self) -> None:
        config = SyntheticHistoryConfig(lookback_bars=50, seed=7)
        first = generate_synthetic_bars("BTCUSDT", config, end_time=_ANCHOR)
        second = generate_synthetic_bars("BTCUSDT", config, end_time=_ANCHOR)
        assert first == second

    def test_a_different_seed_produces_different_data(self) -> None:
        a = generate_synthetic_bars(
            "BTCUSDT", SyntheticHistoryConfig(lookback_bars=50, seed=1), end_time=_ANCHOR
        )
        b = generate_synthetic_bars(
            "BTCUSDT", SyntheticHistoryConfig(lookback_bars=50, seed=2), end_time=_ANCHOR
        )
        assert a != b

    def test_different_symbols_get_independent_series_under_one_seed(self) -> None:
        config = SyntheticHistoryConfig(lookback_bars=50, seed=7)
        btc = generate_synthetic_bars("BTCUSDT", config, end_time=_ANCHOR)
        eth = generate_synthetic_bars("ETHUSDT", config, end_time=_ANCHOR)
        assert [b.close for b in btc] != [b.close for b in eth]

    def test_generates_exactly_the_requested_number_of_bars(self) -> None:
        bars = generate_synthetic_bars(
            "BTCUSDT", SyntheticHistoryConfig(lookback_bars=123), end_time=_ANCHOR
        )
        assert len(bars) == 123

    def test_bars_are_chronologically_ordered_and_evenly_spaced(self) -> None:
        config = SyntheticHistoryConfig(lookback_bars=20, interval=BarInterval.ONE_HOUR)
        bars = generate_synthetic_bars("BTCUSDT", config, end_time=_ANCHOR)
        gap = INTERVAL_TIMEDELTA[BarInterval.ONE_HOUR]
        for previous, current in zip(bars, bars[1:], strict=False):
            assert current.open_time - previous.open_time == gap

    def test_every_generated_bar_satisfies_the_entity_invariants(self) -> None:
        # Construction itself validates; this asserts the generator never
        # produces a bar the domain would reject (e.g. a wick inside the body).
        bars = generate_synthetic_bars(
            "BTCUSDT", SyntheticHistoryConfig(lookback_bars=500), end_time=_ANCHOR
        )
        for bar in bars:
            assert bar.low <= bar.open <= bar.high
            assert bar.low <= bar.close <= bar.high
            assert bar.volume >= 0

    def test_prices_stay_strictly_positive_over_a_long_walk(self) -> None:
        bars = generate_synthetic_bars(
            "BTCUSDT", SyntheticHistoryConfig(lookback_bars=5000), end_time=_ANCHOR
        )
        assert all(bar.close > 0 for bar in bars)
