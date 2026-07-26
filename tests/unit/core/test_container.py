"""Unit tests for core.container."""

from __future__ import annotations

from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.settings import Settings
from core.container import Container, get_container, get_db_session, reset_container
from database.connection import DatabaseConnection
from shared.enums import ServiceLifecycleState


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


class TestContainer:
    def test_starts_in_starting_state(self) -> None:
        container = Container(_sqlite_settings())
        assert container.state is ServiceLifecycleState.STARTING

    async def test_startup_moves_to_ready(self) -> None:
        container = Container(_sqlite_settings())
        await container.startup()
        assert container.state is ServiceLifecycleState.READY

    def test_db_is_created_lazily_and_cached(self) -> None:
        container = Container(_sqlite_settings())
        first = container.db
        second = container.db
        assert isinstance(first, DatabaseConnection)
        assert first is second

    async def test_shutdown_disposes_db_and_moves_to_stopped(self) -> None:
        container = Container(_sqlite_settings())
        _ = container.db  # force creation
        await container.shutdown()
        assert container.state is ServiceLifecycleState.STOPPED

    async def test_shutdown_without_db_access_is_safe(self) -> None:
        container = Container(_sqlite_settings())
        await container.shutdown()  # should not raise, db was never accessed
        assert container.state is ServiceLifecycleState.STOPPED

    def test_defaults_to_process_settings_when_none_given(self) -> None:
        container = Container()
        assert container.settings is not None


class TestGetContainer:
    def test_returns_singleton_across_calls(self) -> None:
        first = get_container(_sqlite_settings())
        second = get_container(_sqlite_settings())
        assert first is second

    def test_reset_clears_the_singleton(self) -> None:
        first = get_container(_sqlite_settings())
        reset_container()
        second = get_container(_sqlite_settings())
        assert first is not second


class TestGetDbSession:
    async def test_yields_a_usable_session_bound_to_the_singleton_container(self) -> None:
        get_container(_sqlite_settings())
        from sqlalchemy import text

        async for session in get_db_session():
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
