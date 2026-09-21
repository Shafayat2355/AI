"""Unit tests for the pure feature computations in
``feature_engineering/definitions/`` -- no I/O, no feature store, no database.

These functions are the foundation Phase 12's reproducibility requirement
rests on, so the properties asserted here are mostly *mathematical* (known
closed-form values, alignment, determinism) rather than "it returns
something".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from feature_engineering.definitions import statistical_features as stats
from feature_engineering.definitions import technical_indicators as ti


@pytest.fixture
def prices() -> pd.Series:
    return pd.Series([float(x) for x in range(1, 51)])


@pytest.fixture
def bars() -> pd.DataFrame:
    n = 50
    close = np.arange(1.0, n + 1.0)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 100.0),
        }
    )


class TestSimpleMovingAverage:
    def test_matches_the_closed_form_mean_of_the_window(self, prices: pd.Series) -> None:
        sma = ti.simple_moving_average(prices, 5)
        # For 1..50, the 5-period SMA at index 4 covers 1..5 -> mean 3.0
        assert sma.iloc[4] == pytest.approx(3.0)
        assert sma.iloc[9] == pytest.approx(8.0)

    def test_leaves_the_unwarmed_window_as_nan_rather_than_partial_means(
        self, prices: pd.Series
    ) -> None:
        sma = ti.simple_moving_average(prices, 5)
        assert sma.iloc[:4].isna().all()
        assert not np.isnan(sma.iloc[4])

    def test_output_is_index_aligned_to_the_input(self, prices: pd.Series) -> None:
        assert list(ti.simple_moving_average(prices, 5).index) == list(prices.index)


class TestRelativeStrengthIndex:
    def test_is_bounded_to_the_zero_hundred_range(self) -> None:
        rng = np.random.default_rng(0)
        noisy = pd.Series(100 + rng.normal(0, 5, 200).cumsum())
        rsi = ti.relative_strength_index(noisy, 14).dropna()
        assert ((rsi >= 0) & (rsi <= 100)).all()

    def test_a_monotonically_rising_series_has_no_losses_and_saturates_high(
        self, prices: pd.Series
    ) -> None:
        # Every delta is +1, so avg_loss is 0 -- this is *maximum* strength,
        # which must not be confused with the flat-window neutral-50 case.
        rsi = ti.relative_strength_index(prices, 14)
        assert rsi.iloc[-1] == pytest.approx(100.0)

    def test_a_monotonically_falling_series_saturates_low(self) -> None:
        falling = pd.Series([float(x) for x in range(50, 0, -1)])
        assert ti.relative_strength_index(falling, 14).iloc[-1] == pytest.approx(0.0)

    def test_a_completely_flat_window_is_neutral_fifty_not_undefined(self) -> None:
        # 0/0: no gains and no losses. Distinct from the no-losses case above.
        flat = pd.Series([42.0] * 30)
        assert ti.relative_strength_index(flat, 14).iloc[-1] == pytest.approx(50.0)

    def test_the_unwarmed_leading_window_stays_nan_rather_than_neutral_fifty(
        self, prices: pd.Series
    ) -> None:
        # An undefined-because-not-enough-data value must remain NaN so the
        # dataset loader drops it, rather than silently becoming a real-looking
        # neutral reading.
        rsi = ti.relative_strength_index(prices, 14)
        assert rsi.iloc[:13].isna().all()


class TestMACD:
    def test_returns_all_three_expected_columns(self, prices: pd.Series) -> None:
        result = ti.macd(prices)
        assert list(result.columns) == ["macd", "macd_signal", "macd_histogram"]

    def test_histogram_is_exactly_macd_minus_signal(self, prices: pd.Series) -> None:
        result = ti.macd(prices).dropna()
        pd.testing.assert_series_equal(
            result["macd_histogram"],
            result["macd"] - result["macd_signal"],
            check_names=False,
        )


class TestAverageTrueRange:
    def test_is_never_negative(self, bars: pd.DataFrame) -> None:
        atr = ti.average_true_range(bars, 14).dropna()
        assert (atr >= 0).all()


class TestLogReturn:
    def test_matches_the_closed_form_log_ratio(self) -> None:
        series = pd.Series([100.0, 110.0])
        assert stats.log_return(series, 1).iloc[1] == pytest.approx(np.log(1.1))

    def test_first_row_is_nan_because_it_has_no_predecessor(self, prices: pd.Series) -> None:
        assert np.isnan(stats.log_return(prices, 1).iloc[0])


class TestRollingZscore:
    def test_a_constant_series_does_not_divide_by_zero(self) -> None:
        constant = pd.Series([5.0] * 30)
        result = stats.rolling_zscore(constant, 10)
        # std is 0 -> replaced with NA -> result is NA, never inf.
        assert not np.isinf(result.to_numpy(dtype="float64", na_value=0.0)).any()


class TestHighLowRangeRatio:
    def test_is_the_intrabar_range_over_close(self, bars: pd.DataFrame) -> None:
        result = stats.high_low_range_ratio(bars)
        expected = (bars["high"] - bars["low"]) / bars["close"]
        pd.testing.assert_series_equal(result, expected)


class TestDeterminism:
    """Phase 12's reproducibility requirement: identical input must give
    bit-identical output, every call."""

    def test_every_indicator_is_deterministic_across_repeated_calls(
        self, prices: pd.Series, bars: pd.DataFrame
    ) -> None:
        pd.testing.assert_series_equal(
            ti.simple_moving_average(prices, 20), ti.simple_moving_average(prices, 20)
        )
        pd.testing.assert_series_equal(
            ti.relative_strength_index(prices, 14), ti.relative_strength_index(prices, 14)
        )
        pd.testing.assert_frame_equal(ti.macd(prices), ti.macd(prices))
        pd.testing.assert_series_equal(
            stats.rolling_volatility(prices, 20), stats.rolling_volatility(prices, 20)
        )
        pd.testing.assert_series_equal(
            ti.average_true_range(bars, 14), ti.average_true_range(bars, 14)
        )
