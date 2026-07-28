"""Alembic migration environment.

Deliberately does not read its database URL from ``alembic.ini``'s
``sqlalchemy.url`` (Alembic's default) -- it calls
``config.settings.get_settings()`` and ``database.connection.create_engine_from_settings``
instead, the exact same functions the running application uses. This means
``alembic upgrade head`` always targets whatever ``DATABASE_URL``/``POSTGRES_*``
environment variables are active (dev/paper/live), with zero connection string
duplicated between this file and the application's own configuration.

``target_metadata = Base.metadata`` is what makes ``alembic revision
--autogenerate`` work: Alembic diffs the live database's schema against every
table registered on ``Base.metadata`` at the time this module runs, so a future
phase adding a concrete mapped model must import it here (see the ``# Import
mapped models`` comment below) for autogenerate to see its table.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from config.settings import get_settings
from database.base import Base
from database.connection import create_engine_from_settings

# Import mapped models here so Base.metadata is populated for autogenerate --
# none exist yet as of Phase 7 (see docs/PHASE7_DATABASE_LAYER.md "Initial
# migration"). A later phase adding e.g. `database.repositories.order_repository`'s
# concrete `OrderModel` adds an import of it here (silencing the resulting
# unused-import lint finding, since the import's only purpose is its side
# effect of registering the table on Base.metadata).

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_dsn() -> str:
    """Resolve the DSN from the application's own Settings, not alembic.ini."""
    return get_settings().database_dsn()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database (``--sql`` mode)."""
    context.configure(
        url=_get_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Build one async engine (via the app's own engine-building code, so pool
    settings/echo/etc. stay consistent with the running application) and run
    migrations against it, then dispose it immediately -- a one-shot migration
    run has no use for a persistent connection pool, but reusing the app's own
    pooled engine briefly is harmless since it's disposed right after."""
    connectable: AsyncEngine = create_engine_from_settings(get_settings())
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Connect and apply migrations directly (the normal ``alembic upgrade`` path)."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
