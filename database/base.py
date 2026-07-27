"""ORM declarative base and session-scoping utilities.

``Base`` is the single ``DeclarativeBase`` every ORM model under
``database/repositories/*`` (and, eventually, mapped ``core/domain`` entities)
must inherit from, so Alembic's autogenerate and ``Base.metadata`` see every table
from one place.

``session_scope`` is a small helper used by the generic repository implementation
in ``database/repositories/base_repository.py`` and by anything else that needs a
short-lived, transactional unit of work outside of FastAPI's request-scoped DI
(scripts, background jobs in ``scheduler/``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class every ORM model inherits from."""


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session bound to one commit/rollback transaction.

    Commits on clean exit, rolls back and re-raises on any exception, and always
    closes the session -- callers never repeat this transaction-management
    boilerplate themselves.
    """
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


__all__ = ["Base", "session_scope"]
