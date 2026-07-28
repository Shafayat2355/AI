"""Unit tests for database.repositories.soft_delete_repository.SoftDeleteRepository."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.mixins import AuditedBase
from database.repositories.soft_delete_repository import SoftDeleteRepository


class _Widget(AuditedBase):
    __tablename__ = "widgets_test_soft_delete_repository"

    name: Mapped[str] = mapped_column(String, nullable=False)


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
def repository(session: AsyncSession) -> SoftDeleteRepository[_Widget, uuid.UUID]:
    return SoftDeleteRepository(session, _Widget)


class TestDelete:
    async def test_sets_deleted_at_instead_of_removing_the_row(
        self, session: AsyncSession, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        await repository.delete(widget.id)

        # The row still physically exists -- fetched via a raw session.get, not
        # through the repository (which would hide it per its own filtering).
        raw = await session.get(_Widget, widget.id)
        assert raw is not None
        assert raw.deleted_at is not None

    async def test_is_a_no_op_for_a_missing_entity(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        await repository.delete(uuid.uuid4())  # should not raise

    async def test_is_a_no_op_for_an_already_deleted_entity(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        await repository.delete(widget.id)
        await repository.delete(widget.id)  # should not raise a second time


class TestGet:
    async def test_returns_none_for_a_soft_deleted_entity_by_default(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        await repository.delete(widget.id)
        assert await repository.get(widget.id) is None

    async def test_returns_a_soft_deleted_entity_when_include_deleted_is_true(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        await repository.delete(widget.id)
        found = await repository.get(widget.id, include_deleted=True)
        assert found is not None
        assert found.name == "alpha"

    async def test_returns_a_non_deleted_entity_normally(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        found = await repository.get(widget.id)
        assert found is not None


class TestList:
    async def test_excludes_soft_deleted_entities_by_default(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        kept = await repository.add(_Widget(name="kept"))
        removed = await repository.add(_Widget(name="removed"))
        await repository.delete(removed.id)

        results = await repository.list()
        names = {widget.name for widget in results}
        assert names == {"kept"}
        assert kept.id in {widget.id for widget in results}

    async def test_includes_soft_deleted_entities_when_requested(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        await repository.add(_Widget(name="kept"))
        removed = await repository.add(_Widget(name="removed"))
        await repository.delete(removed.id)

        results = await repository.list(include_deleted=True)
        assert {widget.name for widget in results} == {"kept", "removed"}


class TestRestore:
    async def test_clears_deleted_at(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        await repository.delete(widget.id)

        restored = await repository.restore(widget.id)
        assert restored is not None
        assert restored.deleted_at is None
        assert await repository.get(widget.id) is not None

    async def test_returns_none_for_a_missing_entity(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        assert await repository.restore(uuid.uuid4()) is None

    async def test_is_a_no_op_but_still_returns_a_never_deleted_entity(
        self, repository: SoftDeleteRepository[_Widget, uuid.UUID]
    ) -> None:
        widget = await repository.add(_Widget(name="alpha"))
        restored = await repository.restore(widget.id)
        assert restored is not None
        assert restored.id == widget.id
