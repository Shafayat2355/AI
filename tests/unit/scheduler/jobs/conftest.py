"""Fixtures shared by scheduler.jobs unit tests that touch the real Container.

Constructs ``Settings`` explicitly (SQLite for the database, matching
``tests/unit/database/``'s and ``tests/integration/database/``'s own Phase
6/7 precedent) rather than relying on ambient ``DATABASE_URL``/``ENVIRONMENT``
environment variables -- the same reason the rest of this codebase's
Container-touching tests do this: it keeps the test suite runnable as a whole
without one test's env-var needs (a real Postgres DSN default, here) breaking
another's (this package's need for a DB that doesn't require a live Postgres
server).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.settings import Settings
from core.container import get_container, reset_container


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


@pytest.fixture(autouse=True)
def _reset_container() -> Iterator[None]:
    """Ensure each test starts from a fresh Container built with SQLite
    settings -- tests that construct one with different Settings (e.g. an
    unreachable Redis host) must not leak that into the next test."""
    reset_container()
    get_container(_sqlite_settings())
    yield
    reset_container()
