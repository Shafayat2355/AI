"""Statistical (as opposed to indicator-library-style technical) feature
computations, sharing this module's contract with
``feature_engineering/definitions/technical_indicators.py``: a
chronologically-ordered per-symbol ``pandas.Series``/``DataFrame`` in, an
aligned ``Series``/``DataFrame`` out, pure and deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_return(prices: pd.Series, periods: int = 1) -> pd.Series:
    """Log return over ``periods`` bars: ``ln(price_t / price_{t-periods})``.

    Preferred over simple percentage return as a *feature* (rather than a
    label) because log returns are additive across time and closer to
    normally distributed, which is what the rolling z-score/volatility
    features below assume.
    """
    return pd.Series(
        data=np.log(prices / prices.shift(periods)), index=prices.index, name=prices.name
    )


def rolling_volatility(prices: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation of 1-period log returns over ``window``
    bars -- the standard realized-volatility proxy."""
    returns = log_return(prices, periods=1)
    return returns.rolling(window=window, min_periods=window).std()


def rolling_zscore(prices: pd.Series, window: int) -> pd.Series:
    """How many rolling standard deviations ``prices`` currently sits from its
    own rolling mean -- a mean-reversion-style feature."""
    mean = prices.rolling(window=window, min_periods=window).mean()
    std = prices.rolling(window=window, min_periods=window).std()
    return (prices - mean) / std.replace(0.0, pd.NA)


def rolling_skewness(prices: pd.Series, window: int) -> pd.Series:
    """Rolling skewness of 1-period log returns over ``window`` bars."""
    returns = log_return(prices, periods=1)
    return returns.rolling(window=window, min_periods=window).skew()


def volume_zscore(volume: pd.Series, window: int) -> pd.Series:
    """How many rolling standard deviations current ``volume`` sits from its
    own rolling mean -- flags unusually high/low trading activity."""
    return rolling_zscore(volume, window)


def high_low_range_ratio(bars: pd.DataFrame) -> pd.Series:
    """Intra-bar range normalized by close: ``(high - low) / close`` -- a
    per-bar (not rolling) volatility proxy. ``bars`` must have ``high``,
    ``low``, ``close`` columns."""
    return (bars["high"] - bars["low"]) / bars["close"]


__all__ = [
    "high_low_range_ratio",
    "log_return",
    "rolling_skewness",
    "rolling_volatility",
    "rolling_zscore",
    "volume_zscore",
]
