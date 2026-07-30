"""Integration test: core.container.Container's cache/redis wiring, end-to-end
against a real Redis server -- proves the whole Phase 8 stack composes through
the actual DI container, not just each piece in isolation (covered by
tests/unit/cache/).
"""

from __future__ import annotations

import uuid

from pydantic import SecretStr

from cache.market_cache import MarketCache
from cache.prediction_cache import PredictionCache
from config.modules.database import DatabaseSettings
from config.modules.redis import RedisSettings
from config.settings import Settings
from core.container import Container, get_cache_manager, get_container, reset_container


def _settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        redis=RedisSettings(key_prefix=f"test:{uuid.uuid4().hex}:"),
    )


class TestContainerCacheProperty:
    async def test_cache_is_created_lazily_and_cached_as_a_singleton(self) -> None:
        container = Container(_settings())
        try:
            first = container.cache
            second = container.cache
            assert first is second
        finally:
            await container.shutdown()

    async def test_accessing_cache_also_creates_the_redis_connection(self) -> None:
        container = Container(_settings())
        try:
            assert container._redis_connection is None  # not yet created
            _ = container.cache
            assert container._redis_connection is not None
        finally:
            await container.shutdown()

    async def test_shutdown_disposes_redis_and_clears_the_cache_manager(self) -> None:
        container = Container(_settings())
        _ = container.cache
        await container.shutdown()
        assert container._redis_connection is None
        assert container._cache_manager is None


class TestCacheManagerThroughTheContainer:
    async def test_prediction_cache_round_trips_through_the_real_container(self) -> None:
        container = Container(_settings())
        try:
            prediction_cache = PredictionCache(container.cache, default_ttl_seconds=60)
            await prediction_cache.set("model-a", "v1", "hash-1", {"direction": "up"})
            assert await prediction_cache.get("model-a", "v1", "hash-1") == {"direction": "up"}
        finally:
            await container.shutdown()

    async def test_market_cache_round_trips_through_the_real_container(self) -> None:
        container = Container(_settings())
        try:
            market_cache = MarketCache(container.cache, default_ttl_seconds=5)
            await market_cache.set_latest_tick("BTCUSDT", {"price": 65000})
            assert await market_cache.get_latest_tick("BTCUSDT") == {"price": 65000}
        finally:
            await container.shutdown()


class TestGetCacheManagerDependency:
    def test_returns_the_process_wide_containers_cache(self) -> None:
        container = get_container(_settings())
        try:
            assert get_cache_manager() is container.cache
        finally:
            reset_container()
