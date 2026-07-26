"""Integration test: database.connection + database.base + database.repositories
wired together through core.container, exercised against a real (in-memory
SQLite) database rather than mocked pieces.

Unlike ``tests/unit/database/test_base_repository.py`` (which builds its own
engine/session directly), this test goes through ``core.container.Container`` --
the same path ``app/api_service/main.py`` uses in production -- to catch wiring
mistakes the unit tests, each scoped to one module, cannot see.
"""

from __future__ import annotations

from pydantic import SecretStr
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from config.modules.database import DatabaseSettings
from config.settings import Settings
from core.container import Container
from database.base import Base
from database.repositories.base_repository import SQLAlchemyRepository


class _Account(Base):
    __tablename__ = "accounts_test_integration"

    id = Column(Integer, primary_key=True)
    display_name = Column(String, nullable=False)


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


class TestContainerBackedRepository:
    async def test_full_round_trip_through_the_container(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        try:
            async with container.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async for session in container.db.session():
                await self._exercise_repository(session)
        finally:
            await container.shutdown()

    @staticmethod
    async def _exercise_repository(session: AsyncSession) -> None:
        repository: SQLAlchemyRepository[_Account, int] = SQLAlchemyRepository(session, _Account)

        created = await repository.add(_Account(id=1, display_name="Primary"))
        assert created.id == 1

        found = await repository.get(1)
        assert found is not None
        assert found.display_name == "Primary"

        await repository.update(_Account(id=1, display_name="Renamed"))
        renamed = await repository.get(1)
        assert renamed is not None
        assert renamed.display_name == "Renamed"

        all_accounts = await repository.list()
        assert len(all_accounts) == 1

        await repository.delete(1)
        assert await repository.get(1) is None

    async def test_readiness_reflects_a_reachable_database_after_startup(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        try:
            assert await container.db.check_connection() is True
        finally:
            await container.shutdown()
