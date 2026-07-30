"""Fixtures shared by every test module under tests/unit/cache/.

Uses ``fakeredis`` (an in-memory, protocol-compatible fake Redis server) rather
than mocking individual method calls -- mirrors ``tests/unit/database/``'s own
precedent of testing against a real, fast, in-memory backend (SQLite there,
fakeredis here) instead of hand-rolled mocks, per
``docs/PHASE3_ENGINEERING_STANDARDS.md``.

Exception: ``cache.distributed_lock.DistributedLock`` is **not** tested here --
redis-py's ``Lock.release()``/``extend()`` use a Lua script (``EVALSHA``),
which fakeredis does not implement. ``DistributedLock`` is tested in
``tests/integration/cache/`` against a real Redis instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis as fake_aioredis
from redis.asyncio import Redis

from config.settings import Settings


class FakeRedisConnection:
    """Minimal stand-in for :class:`cache.redis_client.RedisConnection`.

    Duck-types the one attribute :class:`~cache.cache_manager.CacheManager` and
    :class:`~cache.rate_limit_cache.RateLimitCache` actually read (``.client``)
    -- fakeredis's ``FakeRedis`` is protocol-compatible with
    ``redis.asyncio.Redis`` for every command exercised by these tests
    (GET/SET/DEL/EXISTS/TTL/EXPIRE/INCR/PING).
    """

    def __init__(self, client: Redis) -> None:
        self.client = client


@pytest.fixture
async def fake_redis() -> AsyncIterator[Redis]:
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def fake_redis_connection(fake_redis: Redis) -> FakeRedisConnection:
    return FakeRedisConnection(fake_redis)


@pytest.fixture
def settings() -> Settings:
    return Settings()
