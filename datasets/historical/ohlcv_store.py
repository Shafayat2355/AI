"""Read/write interface to the time-series OHLCV store.

Thin domain-facing wrapper around
``database.repositories.ohlcv_bar_repository.OHLCVBarRepository`` -- the
Postgres table Phase 11's feature computation reads from
(``feature_engineering/offline_pipeline.py``). Also provides
:func:`sync_latest_history`, the integration point
``scheduler/jobs/historical_sync_job.py`` already calls via
``scheduler.jobs.job_result.call_integration_point``.

No real exchange feed is wired up yet -- ``market_data/feed_adapters/`` is
still an unimplemented Phase 2 stub, and standing up a live Binance historical
REST client is out of scope for Phase 11/12 (ML training/model management),
which need a **source of historical bars to build features and labels from**,
not a market-data ingestion service. :func:`sync_latest_history` therefore
backfills with a deterministic, seeded synthetic random walk -- explicitly
*not* real market data, clearly named and documented as such -- so the rest of
the pipeline (feature computation, training, evaluation) has real rows to run
against end-to-end. Swapping this for ``market_data/feed_adapters``-sourced
history later requires no change to any downstream consumer: they all go
through :class:`OHLCVStore`/``OHLCVBarRepository``, never this module's
generator directly.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities.tick import BarInterval, OHLCVBar
from database.repositories.ohlcv_bar_repository import OHLCVBarRepository
from shared.errors.exceptions import InfrastructureError
from shared.logging.logger import get_logger

_logger = get_logger("datasets.historical.ohlcv_store")

#: Wall-clock duration of one bar, per :class:`BarInterval` -- public so
#: ``datasets/schemas/dataset_schema.py`` (gap detection) and
#: ``feature_engineering`` can reason about expected bar spacing without
#: duplicating this table.
INTERVAL_TIMEDELTA: dict[BarInterval, timedelta] = {
    BarInterval.ONE_MINUTE: timedelta(minutes=1),
    BarInterval.FIVE_MINUTE: timedelta(minutes=5),
    BarInterval.FIFTEEN_MINUTE: timedelta(minutes=15),
    BarInterval.ONE_HOUR: timedelta(hours=1),
    BarInterval.FOUR_HOUR: timedelta(hours=4),
    BarInterval.ONE_DAY: timedelta(days=1),
}


class OHLCVStore:
    """Domain-facing read/write access to persisted OHLCV bars.

    Takes an already-open :class:`AsyncSession` and constructs its own
    :class:`OHLCVBarRepository` from it, mirroring how ``database.unit_of_work``
    composes repositories from one session rather than each repository
    managing its own connection.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repository = OHLCVBarRepository(session)

    async def get_history(
        self,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Return persisted bars for ``symbol``/``interval`` in ``[start, end)``,
        chronologically ordered, as framework-free domain entities."""
        rows = await self._repository.list_by_symbol_range(symbol, interval, start, end)
        return [row.to_entity() for row in rows]

    async def save_bars(self, bars: Sequence[OHLCVBar]) -> int:
        """Persist ``bars``, skipping duplicates. Returns the number actually
        inserted."""
        return await self._repository.upsert_many(bars)

    async def latest_open_time(self, symbol: str, interval: BarInterval) -> datetime | None:
        """The most recent persisted ``open_time`` for ``symbol``/``interval``."""
        return await self._repository.latest_open_time(symbol, interval)


@dataclass(frozen=True, slots=True)
class SyntheticHistoryConfig:
    """Parameters for the deterministic synthetic backfill used by
    :func:`sync_latest_history` and :func:`generate_synthetic_bars`."""

    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    interval: BarInterval = BarInterval.ONE_HOUR
    lookback_bars: int = 24 * 90  # 90 days of hourly bars
    seed: int = 42
    starting_price: Decimal = Decimal("30000")
    #: Per-bar log-return volatility, e.g. 0.004 ~ 0.4% per bar.
    volatility: float = 0.004
    #: Slight per-symbol upward/downward bias so symbols are distinguishable.
    drift: float = 0.0001


def generate_synthetic_bars(
    symbol: str,
    config: SyntheticHistoryConfig,
    *,
    end_time: datetime | None = None,
) -> list[OHLCVBar]:
    """Deterministically generate ``config.lookback_bars`` OHLCV bars for
    ``symbol`` ending at ``end_time`` (default: now, floored to the interval).

    A seeded :class:`random.Random` keyed on ``(config.seed, symbol)`` makes
    this reproducible across runs for the same symbol -- required by Phase
    12's reproducibility requirement (the same seed/config must yield the same
    training data). Uses a geometric random walk (log-returns), which is a
    standard, well-understood synthetic price-series model -- not a claim that
    it resembles any particular real market's behavior.
    """
    rng = random.Random(f"{config.seed}:{symbol}")
    interval_delta = INTERVAL_TIMEDELTA[config.interval]
    anchor = (end_time or datetime.now(UTC)).replace(microsecond=0, second=0)
    price = config.starting_price
    bars: list[OHLCVBar] = []

    for i in range(config.lookback_bars, 0, -1):
        open_time = anchor - interval_delta * i
        log_return = rng.gauss(config.drift, config.volatility)
        open_price = price
        close_price = (open_price * Decimal(str(1 + log_return))).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )
        if close_price <= 0:
            close_price = Decimal("0.00000001")
        high_wick = Decimal(str(abs(rng.gauss(0, config.volatility / 2))))
        low_wick = Decimal(str(abs(rng.gauss(0, config.volatility / 2))))
        high_price = max(open_price, close_price) * (Decimal("1") + high_wick)
        low_price = min(open_price, close_price) * (Decimal("1") - low_wick)
        low_price = max(low_price, Decimal("0.00000001"))
        volume = Decimal(str(abs(rng.gauss(1000, 250)))).quantize(Decimal("0.00000001"))

        bars.append(
            OHLCVBar(
                symbol=symbol,
                interval=config.interval,
                open_time=open_time,
                open=open_price.quantize(Decimal("0.00000001")),
                high=high_price.quantize(Decimal("0.00000001")),
                low=low_price.quantize(Decimal("0.00000001")),
                close=close_price,
                volume=volume,
            )
        )
        price = close_price

    return bars


async def sync_latest_history(
    *,
    session: AsyncSession | None = None,
    config: SyntheticHistoryConfig | None = None,
) -> dict[str, int]:
    """Integration point called by ``scheduler.jobs.historical_sync_job``.

    Backfills each symbol in ``config.symbols`` with synthetic history (see
    module docstring) up to a full ``config.lookback_bars`` window, then tops
    up with any bars newer than what is already persisted -- idempotent and
    cheap to re-run. Returns ``{symbol: bars_inserted}``.

    ``session`` is accepted (rather than always resolving one internally) so
    tests and other callers that already hold an open unit-of-work session can
    reuse it; when omitted, a request-scoped session is obtained from the
    process :class:`~core.container.Container`, matching every other
    integration point's convention of resolving its own dependencies when
    called by ``scheduler.jobs.cli``.
    """
    cfg = config or SyntheticHistoryConfig()
    started = datetime.now(UTC)
    _logger.info(
        "ohlcv_sync_started",
        extra={"channel": "application", "symbols": list(cfg.symbols), "interval": cfg.interval},
    )

    async def _run(active_session: AsyncSession) -> dict[str, int]:
        store = OHLCVStore(active_session)
        results: dict[str, int] = {}
        for symbol in cfg.symbols:
            bars = generate_synthetic_bars(symbol, cfg, end_time=started)
            latest = await store.latest_open_time(symbol, cfg.interval)
            if latest is not None:
                bars = [b for b in bars if b.open_time > latest]
            inserted = await store.save_bars(bars)
            results[symbol] = inserted
        return results

    try:
        if session is not None:
            results = await _run(session)
        else:
            from core.container import get_container

            container = get_container()
            async for db_session in container.db.session():
                results = await _run(db_session)
    except Exception as exc:  # pragma: no cover - defensive, re-raised typed
        raise InfrastructureError(f"OHLCV historical sync failed: {exc}") from exc

    _logger.info(
        "ohlcv_sync_completed",
        extra={"channel": "application", "results": results},
    )
    return results


__all__ = [
    "INTERVAL_TIMEDELTA",
    "OHLCVStore",
    "SyntheticHistoryConfig",
    "generate_synthetic_bars",
    "sync_latest_history",
]
