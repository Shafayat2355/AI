"""Unit tests for database.unit_of_work.AsyncUnitOfWork."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.base import Base
from database.unit_of_work import AsyncUnitOfWork


class _Widget(Base):
    __tablename__ = "widgets_test_unit_of_work"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class TestSessionAccess:
    async def test_session_is_available_inside_the_block(
        self, session_factory: async_sessionmaker
    ) -> None:
        async with AsyncUnitOfWork(session_factory) as uow:
            assert uow.session is not None

    def test_session_raises_outside_the_block(
        self, session_factory: async_sessionmaker
    ) -> None:
        uow = AsyncUnitOfWork(session_factory)
        with pytest.raises(RuntimeError, match="outside"):
            _ = uow.session


class TestExplicitCommit:
    async def test_committed_changes_are_visible_after_the_block(
        self, session_factory: async_sessionmaker
    ) -> None:
        async with AsyncUnitOfWork(session_factory) as uow:
            uow.session.add(_Widget(id=1, name="alpha"))
            await uow.commit()

        async with AsyncUnitOfWork(session_factory) as uow:
            result = await uow.session.get(_Widget, 1)
            assert result is not None
            assert result.name == "alpha"


class TestExceptionRollsBack:
    async def test_an_exception_rolls_back_uncommitted_changes(
        self, session_factory: async_sessionmaker
    ) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with AsyncUnitOfWork(session_factory) as uow:
                uow.session.add(_Widget(id=2, name="beta"))
                raise RuntimeError("boom")

        async with AsyncUnitOfWork(session_factory) as uow:
            assert await uow.session.get(_Widget, 2) is None

    async def test_exception_after_a_commit_does_not_undo_the_commit(
        self, session_factory: async_sessionmaker
    ) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async with AsyncUnitOfWork(session_factory) as uow:
                uow.session.add(_Widget(id=3, name="gamma"))
                await uow.commit()
                raise RuntimeError("boom")

        async with AsyncUnitOfWork(session_factory) as uow:
            result = await uow.session.get(_Widget, 3)
            assert result is not None


class TestExitingWithoutCommit:
    async def test_clean_exit_without_commit_rolls_back(
        self, session_factory: async_sessionmaker
    ) -> None:
        async with AsyncUnitOfWork(session_factory) as uow:
            uow.session.add(_Widget(id=4, name="delta"))
            # Deliberately never call uow.commit().

        async with AsyncUnitOfWork(session_factory) as uow:
            assert await uow.session.get(_Widget, 4) is None


class TestExplicitRollback:
    async def test_rollback_discards_pending_changes_before_the_block_exits(
        self, session_factory: async_sessionmaker
    ) -> None:
        async with AsyncUnitOfWork(session_factory) as uow:
            uow.session.add(_Widget(id=5, name="epsilon"))
            await uow.rollback()
            # Add something else and commit that instead, proving the unit of
            # work is still usable after an explicit mid-block rollback.
            uow.session.add(_Widget(id=6, name="zeta"))
            await uow.commit()

        async with AsyncUnitOfWork(session_factory) as uow:
            assert await uow.session.get(_Widget, 5) is None
            assert await uow.session.get(_Widget, 6) is not None


class TestMultipleRepositoriesShareOneTransaction:
    async def test_two_repository_style_additions_commit_together(
        self, session_factory: async_sessionmaker
    ) -> None:
        from database.repositories.base_repository import SQLAlchemyRepository

        async with AsyncUnitOfWork(session_factory) as uow:
            repo_a: SQLAlchemyRepository[_Widget, int] = SQLAlchemyRepository(
                uow.session, _Widget
            )
            repo_b: SQLAlchemyRepository[_Widget, int] = SQLAlchemyRepository(
                uow.session, _Widget
            )
            await repo_a.add(_Widget(id=7, name="eta"))
            await repo_b.add(_Widget(id=8, name="theta"))
            await uow.commit()

        async with AsyncUnitOfWork(session_factory) as uow:
            assert await uow.session.get(_Widget, 7) is not None
            assert await uow.session.get(_Widget, 8) is not None
