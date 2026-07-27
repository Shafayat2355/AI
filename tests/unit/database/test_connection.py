"""Unit tests for database.connection."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from config.modules.database import DatabaseSettings
from config.settings import Settings
from database.connection import (
    DatabaseConnection,
    create_engine_from_settings,
    create_session_factory,
)


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


def _postgres_settings(**database_kwargs: object) -> Settings:
    return Settings(
        database=DatabaseSettings(
            url=SecretStr("postgresql+asyncpg://user:pass@localhost:5432/db"),
            **database_kwargs,  # type: ignore[arg-type]
        )
    )


class TestCreateEngineFromSettings:
    def test_builds_engine_for_sqlite(self) -> None:
        engine = create_engine_from_settings(_sqlite_settings())
        assert isinstance(engine, AsyncEngine)

    def test_builds_engine_for_postgres_with_pool_kwargs(self) -> None:
        settings = _postgres_settings(pool_size=7, max_overflow=3)
        engine = create_engine_from_settings(settings)
        assert isinstance(engine, AsyncEngine)
        pool = engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 7

    def test_sqlite_engine_omits_unsupported_pool_kwargs(self) -> None:
        # Would raise TypeError from SQLAlchemy if pool_size/max_overflow were
        # passed through for a SQLite dialect -- constructing successfully is the
        # assertion.
        engine = create_engine_from_settings(_sqlite_settings())
        assert engine is not None


class TestCreateSessionFactory:
    def test_builds_a_working_session_factory(self) -> None:
        engine = create_engine_from_settings(_sqlite_settings())
        factory = create_session_factory(engine)
        session = factory()
        assert session.bind is engine


class TestDatabaseConnection:
    async def test_session_yields_a_usable_async_session(self) -> None:
        connection = DatabaseConnection(_sqlite_settings())
        try:
            async for session in connection.session():
                from sqlalchemy import text

                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            await connection.dispose()

    async def test_check_connection_true_for_reachable_sqlite(self) -> None:
        connection = DatabaseConnection(_sqlite_settings())
        try:
            assert await connection.check_connection() is True
        finally:
            await connection.dispose()

    async def test_check_connection_false_for_unreachable_database(self) -> None:
        # Port 1 is reserved/unroutable -- guaranteed nothing is listening, so this
        # exercises the failure branch without depending on external infra.
        settings = Settings(
            database=DatabaseSettings(
                url=SecretStr("postgresql+asyncpg://user:pass@localhost:1/db")
            )
        )
        connection = DatabaseConnection(settings)
        try:
            assert await connection.check_connection() is False
        finally:
            await connection.dispose()

    async def test_dispose_is_safe_to_call_even_without_use(self) -> None:
        connection = DatabaseConnection(_sqlite_settings())
        await connection.dispose()  # should not raise

    async def test_engine_property_returns_same_engine(self) -> None:
        connection = DatabaseConnection(_sqlite_settings())
        try:
            assert connection.engine is connection.engine
        finally:
            await connection.dispose()
