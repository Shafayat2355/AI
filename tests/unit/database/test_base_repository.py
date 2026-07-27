"""Unit tests for database.repositories.base_repository.SQLAlchemyRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.base import Base
from database.repositories.base_repository import SQLAlchemyRepository


class _Widget(Base):
    __tablename__ = "widgets_test_repository"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
def repository(session: AsyncSession) -> SQLAlchemyRepository[_Widget, int]:
    return SQLAlchemyRepository(session, _Widget)


class TestGet:
    async def test_returns_none_when_missing(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        assert await repository.get(999) is None

    async def test_returns_entity_when_present(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        await repository.add(_Widget(id=1, name="alpha"))
        found = await repository.get(1)
        assert found is not None
        assert found.name == "alpha"


class TestAdd:
    async def test_persists_and_returns_entity(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        widget = await repository.add(_Widget(id=1, name="alpha"))
        assert widget.id == 1


class TestList:
    async def test_returns_added_entities(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        await repository.add(_Widget(id=1, name="alpha"))
        await repository.add(_Widget(id=2, name="beta"))
        results = await repository.list()
        assert {widget.name for widget in results} == {"alpha", "beta"}

    async def test_respects_limit_and_offset(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        for i in range(1, 6):
            await repository.add(_Widget(id=i, name=f"widget-{i}"))
        results = await repository.list(limit=2, offset=2)
        assert [widget.id for widget in results] == [3, 4]


class TestUpdate:
    async def test_persists_changes(self, repository: SQLAlchemyRepository[_Widget, int]) -> None:
        await repository.add(_Widget(id=1, name="alpha"))
        await repository.update(_Widget(id=1, name="renamed"))
        found = await repository.get(1)
        assert found is not None
        assert found.name == "renamed"


class TestDelete:
    async def test_removes_existing_entity(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        await repository.add(_Widget(id=1, name="alpha"))
        await repository.delete(1)
        assert await repository.get(1) is None

    async def test_is_a_no_op_for_missing_entity(
        self, repository: SQLAlchemyRepository[_Widget, int]
    ) -> None:
        await repository.delete(999)  # should not raise
