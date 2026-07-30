"""Integration test: cache.distributed_lock.DistributedLock against a real Redis
server. Not covered by tests/unit/cache/ -- redis-py's ``Lock.release()``/
``extend()`` use a Lua script (``EVALSHA``), which fakeredis does not
implement (confirmed while building this phase's test suite: fakeredis raises
``unknown command 'evalsha'``), so this class can only be genuinely tested
against a real Redis.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from cache.distributed_lock import DistributedLock, LockAcquisitionError
from cache.redis_client import RedisConnection
from config.modules.redis import RedisSettings
from config.settings import Settings


def _unique_settings() -> Settings:
    return Settings(redis=RedisSettings(key_prefix=f"test:{uuid.uuid4().hex}:"))


@pytest.fixture
def settings() -> Settings:
    return _unique_settings()


@pytest.fixture
async def connection(settings: Settings):
    conn = RedisConnection(settings)
    yield conn
    await conn.dispose()


class TestAcquireRelease:
    async def test_acquire_then_release_succeeds(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock = DistributedLock(connection, settings, "test-lock-1")
        assert await lock.acquire() is True
        assert await lock.locked() is True
        await lock.release()
        assert await lock.locked() is False

    async def test_a_second_non_blocking_acquire_fails_while_held(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock_a = DistributedLock(connection, settings, "test-lock-2")
        lock_b = DistributedLock(connection, settings, "test-lock-2")
        assert await lock_a.acquire() is True
        try:
            assert await lock_b.acquire(blocking=False) is False
        finally:
            await lock_a.release()

    async def test_lock_is_available_again_after_release(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock_a = DistributedLock(connection, settings, "test-lock-3")
        lock_b = DistributedLock(connection, settings, "test-lock-3")
        assert await lock_a.acquire() is True
        await lock_a.release()
        assert await lock_b.acquire(blocking=False) is True
        await lock_b.release()


class TestAsyncContextManager:
    async def test_async_with_acquires_and_releases(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock = DistributedLock(connection, settings, "test-lock-4")
        async with lock:
            assert await lock.locked() is True
        assert await lock.locked() is False

    async def test_releases_even_if_the_block_raises(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock = DistributedLock(connection, settings, "test-lock-5")
        with pytest.raises(ValueError, match="boom"):
            async with lock:
                raise ValueError("boom")
        assert await lock.locked() is False

    async def test_blocks_out_a_concurrent_holder_until_release(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        events: list[str] = []

        async def holder() -> None:
            lock = DistributedLock(
                connection, settings, "test-lock-6", blocking_timeout_seconds=2.0
            )
            async with lock:
                events.append("holder-acquired")
                await asyncio.sleep(0.2)
                events.append("holder-released")

        async def waiter() -> None:
            await asyncio.sleep(0.05)  # ensure holder acquires first
            lock = DistributedLock(
                connection, settings, "test-lock-6", blocking_timeout_seconds=2.0
            )
            async with lock:
                events.append("waiter-acquired")

        await asyncio.gather(holder(), waiter())
        assert events == ["holder-acquired", "holder-released", "waiter-acquired"]

    async def test_raises_lock_acquisition_error_on_timeout(
        self, connection: RedisConnection, settings: Settings
    ) -> None:
        lock_a = DistributedLock(connection, settings, "test-lock-7")
        await lock_a.acquire()
        try:
            lock_b = DistributedLock(
                connection, settings, "test-lock-7", blocking_timeout_seconds=0.1
            )
            with pytest.raises(LockAcquisitionError):
                async with lock_b:
                    pass
        finally:
            await lock_a.release()
