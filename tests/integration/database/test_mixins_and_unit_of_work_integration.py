"""Integration test: database.mixins + database.repositories.soft_delete_repository
+ database.unit_of_work wired together through core.container.Container, against a
real (in-memory SQLite) database -- proving the whole Phase 7 stack composes, not
just each piece in isolation (covered by tests/unit/database/).
"""

from __future__ import annotations

import uuid

from pydantic import SecretStr
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from config.modules.database import DatabaseSettings
from config.settings import Settings
from core.container import Container
from database.base import Base
from database.connection import create_session_factory
from database.mixins import AuditedBase
from database.repositories.soft_delete_repository import SoftDeleteRepository
from database.unit_of_work import AsyncUnitOfWork


class _Position(AuditedBase):
    """Stands in for a future real trading-domain model, exercising every mixin
    (UUID PK, timestamps, soft delete, audit fields) through a real container."""

    __tablename__ = "positions_test_integration"

    symbol: Mapped[str] = mapped_column(String, nullable=False)


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


class TestAuditedModelThroughTheContainer:
    async def test_full_lifecycle_via_soft_delete_repository(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        try:
            async with container.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async for session in container.db.session():
                repository: SoftDeleteRepository[_Position, uuid.UUID] = SoftDeleteRepository(
                    session, _Position
                )

                created = await repository.add(
                    _Position(symbol="BTCUSDT", created_by="strategy-engine")
                )
                await session.commit()
                assert created.created_at is not None
                assert created.deleted_at is None

                await repository.delete(created.id)
                await session.commit()
                assert await repository.get(created.id) is None
                assert await repository.get(created.id, include_deleted=True) is not None

                restored = await repository.restore(created.id)
                await session.commit()
                assert restored is not None
                assert await repository.get(created.id) is not None
        finally:
            await container.shutdown()


class TestUnitOfWorkAcrossMultipleAuditedModels:
    async def test_two_positions_commit_atomically(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        try:
            async with container.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            session_factory = create_session_factory(container.db.engine)
            async with AsyncUnitOfWork(session_factory) as uow:
                repository: SoftDeleteRepository[_Position, uuid.UUID] = SoftDeleteRepository(
                    uow.session, _Position
                )
                await repository.add(_Position(symbol="BTCUSDT"))
                await repository.add(_Position(symbol="ETHUSDT"))
                await uow.commit()

            async for session in container.db.session():
                repository = SoftDeleteRepository(session, _Position)
                symbols = {position.symbol for position in await repository.list()}
                assert symbols == {"BTCUSDT", "ETHUSDT"}
        finally:
            await container.shutdown()

    async def test_a_failure_mid_transaction_rolls_back_both_additions(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        try:
            async with container.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            session_factory = create_session_factory(container.db.engine)
            try:
                async with AsyncUnitOfWork(session_factory) as uow:
                    repository: SoftDeleteRepository[_Position, uuid.UUID] = SoftDeleteRepository(
                        uow.session, _Position
                    )
                    await repository.add(_Position(symbol="BTCUSDT"))
                    await repository.add(_Position(symbol="ETHUSDT"))
                    raise RuntimeError("simulated risk check failure before commit")
            except RuntimeError:
                pass

            async for session in container.db.session():
                repository = SoftDeleteRepository(session, _Position)
                assert await repository.list() == []
        finally:
            await container.shutdown()
