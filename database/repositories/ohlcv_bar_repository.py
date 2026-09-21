"""Concrete persistence for :class:`core.domain.entities.tick.OHLCVBar`.

New in Phase 11 -- the first concrete mapped model/repository pair in this
codebase (``order_repository.py``/``portfolio_repository.py`` remain Phase 2
stubs; this module does not touch them). Backs
``datasets/historical/ohlcv_store.py``, which is what
``feature_engineering/offline_pipeline.py`` reads from to compute features.

Follows the exact pattern ``database/repositories/base_repository.py`` and
``database/mixins.py`` were built for: a mapped model composing ``Base`` with
the reusable mixins, and a repository subclassing
:class:`~database.repositories.base_repository.SQLAlchemyRepository` with that
model's concrete type.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, DateTime, Index, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.domain.entities.tick import BarInterval, OHLCVBar
from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from database.repositories.base_repository import SQLAlchemyRepository


class OHLCVBarModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mapped table for one OHLCV bar.

    Deliberately composes only :class:`~database.mixins.UUIDPrimaryKeyMixin`
    and :class:`~database.mixins.TimestampMixin`, not the full
    :class:`~database.mixins.AuditedBase` -- market data is append-only,
    ingested by a system job rather than a human actor, so soft-delete and
    ``created_by``/``updated_by`` audit columns do not apply here.
    """

    __tablename__ = "ohlcv_bars"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "interval", "open_time", name="uq_ohlcv_bars_symbol_interval_open_time"
        ),
        Index("ix_ohlcv_bars_symbol_interval_open_time", "symbol", "interval", "open_time"),
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(DECIMAL(24, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(DECIMAL(24, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(DECIMAL(24, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(DECIMAL(24, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(DECIMAL(28, 8), nullable=False)

    def to_entity(self) -> OHLCVBar:
        """Map this row to the framework-free :class:`OHLCVBar` domain entity.

        Normalizes ``open_time`` to UTC-aware if the driver returned it naive
        -- SQLite (used by this test suite and local dev, via aiosqlite) has
        no native ``TIMESTAMPTZ`` and round-trips a ``DateTime(timezone=True)``
        column as a naive value despite what was written; PostgreSQL does not
        have this problem. Every timestamp this table ever writes originates
        from :func:`datetime.datetime.now(UTC)` or an explicitly UTC-aware
        value (``datasets/historical/ohlcv_store.py``), so re-attaching UTC on
        a naive read-back is a safe, not merely convenient, assumption.
        """
        open_time = self.open_time
        if open_time.tzinfo is None:
            open_time = open_time.replace(tzinfo=UTC)
        return OHLCVBar(
            symbol=self.symbol,
            interval=BarInterval(self.interval),
            open_time=open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )

    @classmethod
    def from_entity(cls, bar: OHLCVBar) -> OHLCVBarModel:
        """Build a new (unpersisted) row from a domain :class:`OHLCVBar`."""
        return cls(
            symbol=bar.symbol,
            interval=bar.interval.value,
            open_time=bar.open_time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )


class OHLCVBarRepository(SQLAlchemyRepository[OHLCVBarModel, uuid.UUID]):
    """Adds symbol/interval/time-range queries on top of the generic CRUD
    ``SQLAlchemyRepository`` already provides."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OHLCVBarModel)

    async def list_by_symbol_range(
        self,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
    ) -> Sequence[OHLCVBarModel]:
        """Return bars for ``symbol``/``interval`` with ``open_time`` in
        ``[start, end)``, ordered chronologically -- the shape
        ``feature_engineering/offline_pipeline.py`` needs to compute rolling
        features without re-sorting."""
        statement = (
            select(OHLCVBarModel)
            .where(
                OHLCVBarModel.symbol == symbol,
                OHLCVBarModel.interval == interval.value,
                OHLCVBarModel.open_time >= start,
                OHLCVBarModel.open_time < end,
            )
            .order_by(OHLCVBarModel.open_time.asc())
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def latest_open_time(self, symbol: str, interval: BarInterval) -> datetime | None:
        """The most recent ``open_time`` stored for ``symbol``/``interval``, or
        ``None`` if no bars exist yet -- used by
        ``datasets/historical/ohlcv_store.sync_latest_history`` to resume a
        backfill without re-fetching history it already has.

        Normalized to UTC-aware for the same reason :meth:`OHLCVBarModel.to_entity`
        is -- see that method's docstring.
        """
        statement = (
            select(OHLCVBarModel.open_time)
            .where(OHLCVBarModel.symbol == symbol, OHLCVBarModel.interval == interval.value)
            .order_by(OHLCVBarModel.open_time.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        value = result.scalar_one_or_none()
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    async def upsert_many(self, bars: Sequence[OHLCVBar]) -> int:
        """Insert ``bars``, skipping any that already exist for the same
        ``(symbol, interval, open_time)`` -- makes a re-run of the historical
        sync job idempotent rather than raising a unique-constraint error."""
        if not bars:
            return 0
        inserted = 0
        for bar in bars:
            existing = await self._session.execute(
                select(OHLCVBarModel.id).where(
                    OHLCVBarModel.symbol == bar.symbol,
                    OHLCVBarModel.interval == bar.interval.value,
                    OHLCVBarModel.open_time == bar.open_time,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            self._session.add(OHLCVBarModel.from_entity(bar))
            inserted += 1
        await self._session.flush()
        return inserted


__all__ = ["OHLCVBarModel", "OHLCVBarRepository"]
