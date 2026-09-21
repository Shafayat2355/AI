"""Tick entity: normalized market data point shared across the pipeline.

Despite the module's name (kept for compatibility with the Phase 2 scaffold and
``core/ports/market_data_port.py``'s "any market data source" contract), the
concrete entity defined here is an OHLCV *bar* -- one fixed-interval candle for
one symbol -- rather than a single trade print. This is the unit every
consumer added in Phase 11/12 actually needs: ``feature_engineering/`` computes
technical/statistical features over a series of bars, ``datasets/historical``
persists and replays them, and ``training/`` builds labeled datasets from them.
A raw trade-print entity can be added later under its own name (e.g.
``TradeTick``) without changing this one. This module has no framework/DB
dependency; ``database/repositories/ohlcv_bar_repository.py`` maps a
persistence model to and from it rather than the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class BarInterval(StrEnum):
    """Supported OHLCV bar intervals.

    Deliberately a small, closed set matching what ``feature_engineering``'s
    rolling-window features (``technical_indicators.py``) are calibrated
    against -- an arbitrary free-text interval would make window sizes
    (e.g. "20-period SMA") ambiguous.
    """

    ONE_MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    ONE_HOUR = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY = "1d"


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """One immutable OHLCV candle for one symbol/interval, aligned to
    ``open_time``.

    Validated at construction (``__post_init__``) rather than relying on every
    caller to re-check invariants -- a bar that violates ``high >= low`` etc. is
    corrupt data and should never enter the pipeline, not be caught downstream
    after it has already been persisted or fed into a feature computation.
    """

    symbol: str
    interval: BarInterval
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("OHLCVBar.symbol must not be empty")
        if self.open_time.tzinfo is None:
            raise ValueError("OHLCVBar.open_time must be timezone-aware")
        if self.high < self.low:
            raise ValueError(
                f"OHLCVBar.high ({self.high}) must be >= OHLCVBar.low ({self.low})"
            )
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"OHLCVBar.open ({self.open}) must be within [low={self.low}, high={self.high}]"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"OHLCVBar.close ({self.close}) must be within "
                f"[low={self.low}, high={self.high}]"
            )
        if self.volume < 0:
            raise ValueError(f"OHLCVBar.volume ({self.volume}) must be >= 0")

    @property
    def typical_price(self) -> Decimal:
        """(high + low + close) / 3 -- used as the price series several
        technical indicators are computed against instead of ``close`` alone."""
        return (self.high + self.low + self.close) / Decimal(3)

    @property
    def is_bullish(self) -> bool:
        """Whether this bar closed above where it opened."""
        return self.close > self.open


__all__ = ["BarInterval", "OHLCVBar"]
