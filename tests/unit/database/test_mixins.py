"""Unit tests for database.mixins."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.mixins import (
    AuditedBase,
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class _Widget(AuditedBase):
    """A model exercising every mixin at once, via the AuditedBase convenience combo."""

    __tablename__ = "widgets_test_mixins_audited"

    name: Mapped[str] = mapped_column(String, nullable=False)


class _BareTimestamped(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A model composing only UUID PK + timestamps -- no soft delete, no audit --
    proving the mixins are independently usable, not only via AuditedBase."""

    __tablename__ = "widgets_test_mixins_bare_timestamped"

    label: Mapped[str] = mapped_column(String, nullable=False)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


class TestUUIDPrimaryKeyMixin:
    async def test_generates_a_uuid_id_by_default(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.flush()
        assert isinstance(widget.id, uuid.UUID)

    async def test_ids_are_unique_across_instances(self, session: AsyncSession) -> None:
        a, b = _Widget(name="a"), _Widget(name="b")
        session.add_all([a, b])
        await session.flush()
        assert a.id != b.id

    async def test_id_is_none_before_flush_and_set_after(self, session: AsyncSession) -> None:
        # mapped_column(default=...) is applied by SQLAlchemy during flush, not
        # at __init__ time -- this documents that behavior explicitly rather
        # than leaving it as an implicit assumption.
        widget = _Widget(name="alpha")
        assert widget.id is None
        session.add(widget)
        await session.flush()
        assert isinstance(widget.id, uuid.UUID)


class TestTimestampMixin:
    async def test_created_at_and_updated_at_are_set_on_insert(
        self, session: AsyncSession
    ) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.flush()
        assert widget.created_at is not None
        assert widget.updated_at is not None

    async def test_timestamps_are_timezone_aware(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.flush()
        assert widget.created_at.tzinfo is not None
        assert widget.updated_at.tzinfo is not None

    async def test_updated_at_changes_on_update_but_created_at_does_not(
        self, session: AsyncSession
    ) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.commit()
        original_created_at = widget.created_at
        original_updated_at = widget.updated_at

        widget.name = "renamed"
        await session.commit()

        assert widget.created_at == original_created_at
        assert widget.updated_at >= original_updated_at

    async def test_works_without_the_other_mixins(self, session: AsyncSession) -> None:
        row = _BareTimestamped(label="standalone")
        session.add(row)
        await session.flush()
        assert row.created_at is not None
        assert not hasattr(row, "deleted_at")


class TestSoftDeleteMixin:
    async def test_deleted_at_defaults_to_none(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.flush()
        assert widget.deleted_at is None
        assert widget.is_deleted is False

    async def test_is_deleted_reflects_a_set_deleted_at(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha")
        widget.deleted_at = datetime.now(UTC)
        assert widget.is_deleted is True

    def test_mixin_is_usable_standalone(self) -> None:
        class _Standalone(SoftDeleteMixin):
            pass

        instance = _Standalone()
        instance.deleted_at = None
        assert instance.is_deleted is False


class TestAuditMixin:
    async def test_created_by_and_updated_by_default_to_none(
        self, session: AsyncSession
    ) -> None:
        widget = _Widget(name="alpha")
        session.add(widget)
        await session.flush()
        assert widget.created_by is None
        assert widget.updated_by is None

    async def test_can_be_set_explicitly(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha", created_by="trader-1", updated_by="trader-1")
        session.add(widget)
        await session.flush()
        assert widget.created_by == "trader-1"

    def test_mixin_is_usable_standalone(self) -> None:
        class _Standalone(AuditMixin):
            pass

        instance = _Standalone()
        assert not hasattr(instance, "id")  # no UUID PK unless that mixin is also composed


class TestAuditedBase:
    async def test_roundtrips_through_a_real_session(self, session: AsyncSession) -> None:
        widget = _Widget(name="alpha", created_by="system")
        session.add(widget)
        await session.commit()

        fetched = await session.get(_Widget, widget.id)
        assert fetched is not None
        assert fetched.name == "alpha"
        assert fetched.created_by == "system"
        assert fetched.deleted_at is None
        assert fetched.created_at is not None

    def test_is_abstract_and_never_mapped_directly(self) -> None:
        assert AuditedBase.__abstract__ is True
