"""Async Unit of Work: coordinate several repository operations under one transaction.

Phase 6's ``database.base.session_scope`` already provides commit-on-success /
rollback-on-exception for a single ``async with`` block -- this module wraps that
same guarantee in an object with explicit ``commit``/``rollback`` methods, for the
common case where a use case needs to decide *mid-transaction* whether to commit
(e.g. only after a risk check inside the block passes), rather than always
committing on clean exit.

Not wired into ``core.container.Container`` or FastAPI's ``Depends()`` chain in
this phase -- see ``docs/PHASE7_DATABASE_LAYER.md`` for why that wiring decision is
left for explicit approval rather than made silently here.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.logging.logger import get_logger

_logger = get_logger("database.unit_of_work")


class AsyncUnitOfWork:
    """One transactional unit of work spanning any number of repositories.

    Usage::

        async with AsyncUnitOfWork(session_factory) as uow:
            orders = OrderRepository(uow.session)
            portfolio = PortfolioRepository(uow.session)
            await orders.add(new_order)
            await portfolio.update(updated_position)
            await uow.commit()
        # commit() was called explicitly above; if the block raises or exits
        # without calling commit(), __aexit__ rolls back instead.

    Every repository constructed from ``uow.session`` participates in the same
    transaction automatically -- they all share the one ``AsyncSession``, exactly
    like ``core.container.get_db_session``'s request-scoped session already gives
    a single FastAPI request, just with an explicit commit point instead of an
    implicit one.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    @property
    def session(self) -> AsyncSession:
        """The transaction's shared session. Only valid inside the ``async with`` block."""
        if self._session is None:
            raise RuntimeError(
                "AsyncUnitOfWork.session accessed outside an 'async with' block"
            )
        return self._session

    async def __aenter__(self) -> AsyncUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._session is not None  # __aenter__ always runs first
        try:
            if exc_type is not None:
                await self._session.rollback()
            elif not self._committed:
                # Exited cleanly but the caller never called commit() -- treat
                # that as "decided not to persist", not an error, and roll back
                # rather than silently committing on their behalf.
                await self._session.rollback()
                _logger.warning(
                    "unit_of_work_exited_without_commit",
                    extra={"channel": "application"},
                )
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """Commit the transaction. Call at most once per unit of work."""
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Roll back the transaction explicitly, before the block would otherwise exit."""
        await self.session.rollback()
        self._committed = False


__all__ = ["AsyncUnitOfWork"]
