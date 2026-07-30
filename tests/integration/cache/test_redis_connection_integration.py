"""Integration test: cache.redis_client.RedisConnection against a real Redis
server (not fakeredis) -- proves the actual connection pool, PING-based health
check, retry helper, and pipeline context manager work against the real
protocol, not just fakeredis's reimplementation of it.

Requires a reachable Redis (``docker-compose up redis``, or a local
``redis-server``) at the settings' configured host/port -- see
``docs/PHASE8_REDIS_INFRASTRUCTURE.md`` "Testing strategy".
"""

from __future__ import annotations

import uuid

import pytest

from cache.redis_client import RedisConnection
from config.modules.redis import RedisSettings
from config.settings import Settings


def _unique_settings() -> Settings:
    # A random key_prefix per test run avoids collisions with anything else
    # using this same real Redis instance concurrently.
    return Settings(redis=RedisSettings(key_prefix=f"test:{uuid.uuid4().hex}:"))


@pytest.fixture
async def connection():
    conn = RedisConnection(_unique_settings())
    yield conn
    await conn.dispose()


class TestCheckConnection:
    async def test_returns_true_against_a_reachable_redis(
        self, connection: RedisConnection
    ) -> None:
        assert await connection.check_connection() is True

    async def test_returns_false_against_an_unreachable_redis(self) -> None:
        unreachable = Settings(
            redis=RedisSettings(host="127.0.0.1", port=1, key_prefix="test:unreachable:")
        )
        conn = RedisConnection(unreachable)
        try:
            assert await conn.check_connection() is False
        finally:
            await conn.dispose()


class TestConnectWithRetry:
    async def test_succeeds_immediately_against_a_reachable_redis(
        self, connection: RedisConnection
    ) -> None:
        await connection.connect_with_retry()  # should not raise

    async def test_retries_then_raises_against_an_unreachable_redis(self) -> None:
        unreachable = Settings(
            redis=RedisSettings(host="127.0.0.1", port=1, key_prefix="test:unreachable-retry:")
        )
        conn = RedisConnection(unreachable)
        try:
            with pytest.raises(Exception):  # noqa: B017 - exact driver exception varies
                await conn.connect_with_retry(max_attempts=2, backoff_seconds=0.01)
        finally:
            await conn.dispose()


class TestClientRoundTrip:
    async def test_set_and_get_a_real_value(self, connection: RedisConnection) -> None:
        await connection.client.set("integration-key", b"integration-value")
        assert await connection.client.get("integration-key") == b"integration-value"
        await connection.client.delete("integration-key")

    async def test_binary_payloads_round_trip_without_utf8_corruption(
        self, connection: RedisConnection
    ) -> None:
        # Bytes that are not valid UTF-8 -- would be corrupted if the pool were
        # built with decode_responses=True (see cache/redis_client.py's docstring).
        payload = b"\xff\xfe\x00\x01binary-garbage"
        await connection.client.set("binary-key", payload)
        assert await connection.client.get("binary-key") == payload
        await connection.client.delete("binary-key")


class TestPipeline:
    async def test_pipeline_batches_commands_atomically(self, connection: RedisConnection) -> None:
        async with connection.pipeline() as pipe:
            pipe.set("pipe-key-1", b"a")
            pipe.set("pipe-key-2", b"b")
            await pipe.execute()
        assert await connection.client.get("pipe-key-1") == b"a"
        assert await connection.client.get("pipe-key-2") == b"b"
        await connection.client.delete("pipe-key-1", "pipe-key-2")


class TestDispose:
    async def test_dispose_is_safe_to_call_and_closes_the_pool(self) -> None:
        conn = RedisConnection(_unique_settings())
        await conn.check_connection()
        await conn.dispose()  # should not raise
