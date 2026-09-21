"""Technical indicator feature computations, shared by the offline (training)
and online (materialized-to-Redis) paths.

Every function here takes a chronologically-ordered ``pandas.Series`` of
prices (or a ``DataFrame`` of OHLCV bars) for a *single* symbol and returns a
``Series`` aligned to the same index -- callers apply these per-symbol group
(see ``feature_engineering/offline_pipeline.py``), never across symbols, since
mixing series from different instruments into one rolling window would be
meaningless. Pure, deterministic, no I/O -- these are exactly the functions
Phase 12's reproducibility requirement depends on: same input bars in, same
feature values out, every time.
"""

from __future__ import annotations

import pandas as pd


def simple_moving_average(prices: pd.Series, window: int) -> pd.Series:
    """SMA over ``window`` periods."""
    return prices.rolling(window=window, min_periods=window).mean()


def exponential_moving_average(prices: pd.Series, span: int) -> pd.Series:
    """EMA with the given ``span`` (adjust=False -- the standard recursive
    EMA definition, not the pandas default "adjusted" weighting)."""
    return prices.ewm(span=span, adjust=False, min_periods=span).mean()


def momentum(prices: pd.Series, window: int) -> pd.Series:
    """Percentage price change over ``window`` periods:
    ``(price_t / price_{t-window}) - 1``."""
    return prices.pct_change(periods=window)


def relative_strength_index(prices: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI over ``window`` periods, in ``[0, 100]``.

    Uses a simple rolling mean of gains/losses rather than Wilder's original
    smoothing recursion -- a documented, standard simplification (the
    "cutler's RSI" variant) that keeps this function stateless and vectorized
    like every other indicator here, at the cost of very slightly different
    values than the original recursive formula during the warm-up window.

    The zero-``avg_loss`` case is handled explicitly rather than via a blanket
    ``fillna``: a window with no down moves is *maximum* strength (RSI 100),
    which is a different thing from a window that has not warmed up yet (RSI
    undefined -> ``NaN``, left for the caller to drop). Collapsing both to a
    neutral 50 would silently feed a wrong, plausible-looking value into
    training.
    """
    delta = prices.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.rolling(window=window, min_periods=window).mean()
    avg_loss = losses.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # avg_loss == 0 with some gain -> rs is +inf -> rsi already evaluates to
    # 100, but 0/0 (a completely flat window) yields NaN; treat that as
    # neutral 50, and leave the unwarmed leading window as NaN.
    flat_window = (avg_loss == 0) & (avg_gain == 0)
    rsi = rsi.mask(flat_window, 50.0)
    return rsi


def macd(
    prices: pd.Series, fast_span: int = 12, slow_span: int = 26, signal_span: int = 9
) -> pd.DataFrame:
    """MACD line, signal line, and histogram.

    Returns a three-column ``DataFrame`` (``macd``, ``macd_signal``,
    ``macd_histogram``) rather than three separate calls, since all three
    share the same underlying fast/slow EMAs and recomputing them per-column
    would triple the work for no benefit.
    """
    fast_ema = exponential_moving_average(prices, fast_span)
    slow_ema = exponential_moving_average(prices, slow_span)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_span, adjust=False, min_periods=signal_span).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_histogram": histogram}
    )


def bollinger_band_width(prices: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """Bollinger Band width, normalized by the moving average: a compact
    volatility/"squeeze" indicator: ``(upper - lower) / sma``."""
    sma = simple_moving_average(prices, window)
    std = prices.rolling(window=window, min_periods=window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return (upper - lower) / sma


def average_true_range(bars: pd.DataFrame, window: int = 14) -> pd.Series:
    """ATR over ``window`` periods. ``bars`` must have ``high``, ``low``,
    ``close`` columns, chronologically ordered."""
    prev_close = bars["close"].shift(1)
    true_range = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


__all__ = [
    "average_true_range",
    "bollinger_band_width",
    "exponential_moving_average",
    "macd",
    "momentum",
    "relative_strength_index",
    "simple_moving_average",
]
