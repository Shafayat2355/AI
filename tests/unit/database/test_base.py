"""Unit tests for database.base (Base, session_scope)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.modules.database import DatabaseSettings
from config.settings import Settings
from database.base import Base, session_scope


class _Widget(Base):
    __tablename__ = "widgets_test_base"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


@pytest.fixture
async def sqlite_session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class TestBase:
    def test_settings_sqlite_override_is_constructible(self) -> None:
        # Sanity check the pattern every other DB test in this suite relies on.
        settings = Settings(
            database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:"))
        )
        assert settings.database_dsn() == "sqlite+aiosqlite:///:memory:"


class TestSessionScope:
    async def test_commits_on_success(self, sqlite_session_factory: async_sessionmaker) -> None:
        async with session_scope(sqlite_session_factory) as session:
            session.add(_Widget(id=1, name="alpha"))

        async with session_scope(sqlite_session_factory) as session:
            result = await session.get(_Widget, 1)
            assert result is not None
            assert result.name == "alpha"

    async def test_rolls_back_and_reraises_on_error(
        self, sqlite_session_factory: async_sessionmaker
    ) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with session_scope(sqlite_session_factory) as session:
                session.add(_Widget(id=2, name="beta"))
                raise RuntimeError("boom")

        async with session_scope(sqlite_session_factory) as session:
            result = await session.get(_Widget, 2)
            assert result is None
