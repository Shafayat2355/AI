"""Application-lifetime dependency-injection container.

``config/di.py`` already provides fine-grained, per-request-safe providers for
individual settings modules (``get_redis_settings``, etc.) -- those stay as-is,
since a settings object is cheap to resolve on every call. ``Container`` exists one
level up: it owns the handful of resources that are expensive to create, must be
created exactly once per process, and must be explicitly disposed on shutdown (right
now: the database engine/session factory in ``database.connection.DatabaseConnection``).
A composition root (``app/*_service/main.py``) builds one ``Container`` in its
FastAPI ``lifespan`` handler, stores it on ``app.state.container``, and disposes it
on shutdown via :meth:`Container.shutdown`.

This module intentionally owns process-lifetime *infrastructure* only -- it does
not construct domain services or repositories (``core/use_cases/*``,
``database/repositories/*``), since none are implemented yet as of Phase 6. Later
phases that add a concrete use case are expected to add a corresponding
``Container`` property/factory method here rather than each service wiring its own
dependencies ad hoc.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings, get_settings
from database.connection import DatabaseConnection
from shared.enums import ServiceLifecycleState
from shared.logging.logger import get_logger

_logger = get_logger("core.container")


class Container:
    """Owns and lazily initializes this process's expensive, long-lived resources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.state: ServiceLifecycleState = ServiceLifecycleState.STARTING
        self._db_connection: DatabaseConnection | None = None

    @property
    def db(self) -> DatabaseConnection:
        """The process's single :class:`DatabaseConnection`, created on first access."""
        if self._db_connection is None:
            self._db_connection = DatabaseConnection(self.settings)
        return self._db_connection

    async def startup(self) -> None:
        """Mark the container ready. Idempotent; safe to call once from ``lifespan``.

        Resources themselves (e.g. :attr:`db`) are created lazily on first access
        rather than here, so a service that never touches the database never pays
        for an engine it does not use.
        """
        self.state = ServiceLifecycleState.READY
        _logger.info("container_started", extra={"channel": "application"})

    async def shutdown(self) -> None:
        """Release every resource this container created. Idempotent."""
        self.state = ServiceLifecycleState.DRAINING
        if self._db_connection is not None:
            await self._db_connection.dispose()
            self._db_connection = None
        self.state = ServiceLifecycleState.STOPPED
        _logger.info("container_stopped", extra={"channel": "application"})


_container: Container | None = None


def get_container(settings: Settings | None = None) -> Container:
    """Return the process-wide :class:`Container` singleton, creating it if needed.

    Mirrors ``config.factory.SettingsFactory.create``'s caching shape so
    composition roots and FastAPI ``Depends()`` providers share one instance.
    """
    global _container
    if _container is None:
        _container = Container(settings)
    return _container


def reset_container() -> None:
    """Drop the cached :class:`Container` singleton.

    Does **not** dispose its resources -- callers that need a clean shutdown call
    :meth:`Container.shutdown` first (as ``app/api_service/main.py``'s ``lifespan``
    does). Intended for test teardown, mirroring
    ``config.factory.SettingsFactory.clear_cache``.
    """
    global _container
    _container = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a request-scoped :class:`AsyncSession`.

    Usage: ``session: AsyncSession = Depends(get_db_session)``.
    """
    container = get_container()
    async for session in container.db.session():
        yield session


__all__ = ["Container", "get_container", "get_db_session", "reset_container"]
