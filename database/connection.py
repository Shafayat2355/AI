"""Database connection/session factory shared by repository implementations.

Builds exactly one ``AsyncEngine`` per process from ``config.settings.Settings``
(via ``Settings.database_dsn()`` plus ``config.modules.database.DatabaseSettings``'s
pool knobs), and exposes an async session factory used both by
``database/repositories/*`` implementations and by ``core.container.Container``'s
FastAPI dependency wiring.

Creating an ``AsyncEngine`` does not itself open a network connection (SQLAlchemy
connects lazily, on first use) -- :meth:`DatabaseConnection.check_connection` is the
one method here that actually talks to the database, used by a readiness probe that
chooses to include database connectivity in its check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.modules.database import DatabaseSettings
from config.settings import Settings
from shared.logging.logger import get_logger
from shared.logging.retry import log_retries_async

_logger = get_logger("database.connection")

#: Backends whose SQLAlchemy dialect does not accept pool-sizing kwargs (SQLite's
#: pool is either a single connection or unbounded, never a fixed-size pool) --
#: used so the same engine-building code works against both Postgres (production)
#: and an in-memory SQLite database (unit/integration tests), per
#: ``docs/PHASE3_ENGINEERING_STANDARDS.md``'s "test against the real interface,
#: not a hand-rolled fake" guidance.
_NO_POOL_SIZING_BACKENDS = frozenset({"sqlite"})


def _engine_kwargs(dsn: str, database_settings: DatabaseSettings) -> dict[str, Any]:
    """Build ``create_async_engine`` kwargs from ``database_settings``, adapted to
    ``dsn``'s backend."""
    kwargs: dict[str, Any] = {"echo": database_settings.echo, "pool_pre_ping": True}
    backend = make_url(dsn).get_backend_name()
    if backend not in _NO_POOL_SIZING_BACKENDS:
        kwargs["pool_size"] = database_settings.pool_size
        kwargs["max_overflow"] = database_settings.max_overflow
        kwargs["pool_timeout"] = database_settings.pool_timeout_seconds
        kwargs["pool_recycle"] = database_settings.pool_recycle_seconds
    return kwargs


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Build a new :class:`AsyncEngine` from a fully-resolved :class:`Settings`."""
    dsn = settings.database_dsn()
    return create_async_engine(dsn, **_engine_kwargs(dsn, settings.database))


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the async session factory bound to ``engine``.

    ``expire_on_commit=False`` so an entity returned from a repository method
    remains usable (e.g. serialized into an API response) after its owning
    transaction has committed, without triggering a lazy reload.
    """
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class DatabaseConnection:
    """Owns one ``AsyncEngine``/session-factory pair for the lifetime of a process.

    Constructed once by ``core.container.Container`` at startup and disposed once
    at shutdown -- never constructed per-request. Use :meth:`session` as a FastAPI
    dependency (via ``core.container.get_db_session``) to get a request-scoped
    ``AsyncSession``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_engine_from_settings(settings)
        self._session_factory = create_session_factory(self._engine)

    @property
    def engine(self) -> AsyncEngine:
        """The underlying SQLAlchemy async engine."""
        return self._engine

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a new, request-scoped :class:`AsyncSession`.

        An async generator (rather than a plain factory method) so it can be used
        directly as a FastAPI ``Depends()`` provider -- see
        ``core.container.get_db_session``.
        """
        async with self._session_factory() as session:
            yield session

    async def check_connection(self) -> bool:
        """Attempt a lightweight round-trip query; return whether it succeeded.

        Never raises -- a connectivity failure is an expected, reportable readiness
        result, not a process-level error, so it is caught and logged here rather
        than propagated.
        """
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            _logger.warning(
                "database_connectivity_check_failed",
                extra={"channel": "application"},
                exc_info=True,
            )
            return False

    async def connect_with_retry(
        self, *, max_attempts: int | None = None, backoff_seconds: float | None = None
    ) -> None:
        """Verify connectivity at startup, retrying with backoff before giving up.

        Opt-in -- not called automatically by ``core.container.Container.startup``
        (see ``docs/PHASE7_DATABASE_LAYER.md`` for why). Useful for a composition
        root that wants to fail fast (or wait out a container-orchestration
        startup race, e.g. the app container winning a race against Postgres
        still initializing in ``docker-compose``) rather than silently serving
        traffic against a database that was never reachable.

        Defaults come from ``DatabaseSettings.connect_retry_attempts``/
        ``connect_retry_backoff_seconds`` (configurable per environment) when not
        passed explicitly.

        Raises the underlying connection exception (via
        ``shared.logging.retry.log_retries_async``, which logs every attempt)
        once attempts are exhausted -- unlike :meth:`check_connection`, which
        never raises, because a caller of *this* method has explicitly asked to
        treat exhausted retries as fatal.
        """
        resolved_max_attempts = max_attempts or self._settings.database.connect_retry_attempts
        resolved_backoff = backoff_seconds or self._settings.database.connect_retry_backoff_seconds

        @log_retries_async(
            max_attempts=resolved_max_attempts,
            backoff_seconds=resolved_backoff,
            exceptions=(Exception,),
            operation="database.connect_with_retry",
        )
        async def _attempt() -> None:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        await _attempt()

    async def dispose(self) -> None:
        """Close every pooled connection. Called once, during graceful shutdown."""
        await self._engine.dispose()
        _logger.info("database_engine_disposed", extra={"channel": "application"})


__all__ = ["DatabaseConnection", "create_engine_from_settings", "create_session_factory"]
