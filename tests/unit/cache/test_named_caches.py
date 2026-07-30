"""Unit tests for cache.prediction_cache, cache.market_cache, cache.session_cache,
and cache.rate_limit_cache."""

from __future__ import annotations

import pytest

from cache.cache_manager import CacheManager
from cache.market_cache import MarketCache
from cache.prediction_cache import PredictionCache
from cache.rate_limit_cache import RateLimitCache
from cache.session_cache import SessionCache
from config.settings import Settings
from tests.unit.cache.conftest import FakeRedisConnection


@pytest.fixture
def cache_manager(fake_redis_connection: FakeRedisConnection, settings: Settings) -> CacheManager:
    return CacheManager(fake_redis_connection, settings)  # type: ignore[arg-type]


class TestPredictionCache:
    @pytest.fixture
    def prediction_cache(self, cache_manager: CacheManager) -> PredictionCache:
        return PredictionCache(cache_manager, default_ttl_seconds=300)

    async def test_get_is_none_on_a_miss(self, prediction_cache: PredictionCache) -> None:
        assert await prediction_cache.get("lstm", "v1", "hash-abc") is None

    async def test_set_then_get_round_trips(self, prediction_cache: PredictionCache) -> None:
        prediction = {"direction": "up", "confidence": 0.87}
        await prediction_cache.set("lstm", "v1", "hash-abc", prediction)
        assert await prediction_cache.get("lstm", "v1", "hash-abc") == prediction

    async def test_different_model_versions_do_not_collide(
        self, prediction_cache: PredictionCache
    ) -> None:
        await prediction_cache.set("lstm", "v1", "hash-abc", {"direction": "up"})
        await prediction_cache.set("lstm", "v2", "hash-abc", {"direction": "down"})
        assert await prediction_cache.get("lstm", "v1", "hash-abc") == {"direction": "up"}
        assert await prediction_cache.get("lstm", "v2", "hash-abc") == {"direction": "down"}

    async def test_invalidate_removes_the_entry(self, prediction_cache: PredictionCache) -> None:
        await prediction_cache.set("lstm", "v1", "hash-abc", {"direction": "up"})
        assert await prediction_cache.invalidate("lstm", "v1", "hash-abc") is True
        assert await prediction_cache.get("lstm", "v1", "hash-abc") is None


class TestMarketCache:
    @pytest.fixture
    def market_cache(self, cache_manager: CacheManager) -> MarketCache:
        return MarketCache(cache_manager, default_ttl_seconds=5)

    async def test_get_latest_tick_is_none_on_a_miss(self, market_cache: MarketCache) -> None:
        assert await market_cache.get_latest_tick("BTCUSDT") is None

    async def test_set_then_get_round_trips(self, market_cache: MarketCache) -> None:
        tick = {"price": 65000.5, "volume": 1.2}
        await market_cache.set_latest_tick("BTCUSDT", tick)
        assert await market_cache.get_latest_tick("BTCUSDT") == tick

    async def test_different_symbols_do_not_collide(self, market_cache: MarketCache) -> None:
        await market_cache.set_latest_tick("BTCUSDT", {"price": 65000})
        await market_cache.set_latest_tick("ETHUSDT", {"price": 3400})
        assert await market_cache.get_latest_tick("BTCUSDT") == {"price": 65000}
        assert await market_cache.get_latest_tick("ETHUSDT") == {"price": 3400}

    async def test_invalidate_removes_the_tick(self, market_cache: MarketCache) -> None:
        await market_cache.set_latest_tick("BTCUSDT", {"price": 65000})
        assert await market_cache.invalidate("BTCUSDT") is True
        assert await market_cache.get_latest_tick("BTCUSDT") is None


class TestSessionCache:
    @pytest.fixture
    def session_cache(self, cache_manager: CacheManager) -> SessionCache:
        return SessionCache(cache_manager, default_ttl_seconds=1800)

    async def test_get_is_none_on_a_miss(self, session_cache: SessionCache) -> None:
        assert await session_cache.get("session-1") is None

    async def test_set_then_get_round_trips(self, session_cache: SessionCache) -> None:
        state = {"user_id": "u1", "subscriptions": ["BTCUSDT"]}
        await session_cache.set("session-1", state)
        assert await session_cache.get("session-1") == state

    async def test_touch_extends_ttl_without_changing_state(
        self, session_cache: SessionCache, cache_manager: CacheManager
    ) -> None:
        await session_cache.set("session-1", {"user_id": "u1"}, ttl_seconds=10)
        assert await session_cache.touch("session-1", ttl_seconds=999) is True
        assert await session_cache.get("session-1") == {"user_id": "u1"}

    async def test_touch_on_a_missing_session_returns_false(
        self, session_cache: SessionCache
    ) -> None:
        assert await session_cache.touch("missing-session") is False

    async def test_invalidate_ends_the_session(self, session_cache: SessionCache) -> None:
        await session_cache.set("session-1", {"user_id": "u1"})
        assert await session_cache.invalidate("session-1") is True
        assert await session_cache.get("session-1") is None


class TestRateLimitCache:
    @pytest.fixture
    def rate_limit_cache(
        self, fake_redis_connection: FakeRedisConnection, settings: Settings
    ) -> RateLimitCache:
        return RateLimitCache(fake_redis_connection, settings, default_window_seconds=60)  # type: ignore[arg-type]

    async def test_first_request_is_not_exceeded(self, rate_limit_cache: RateLimitCache) -> None:
        result = await rate_limit_cache.increment_and_check("client-1", limit=5)
        assert result.count == 1
        assert result.exceeded is False

    async def test_counter_increments_across_calls(self, rate_limit_cache: RateLimitCache) -> None:
        await rate_limit_cache.increment_and_check("client-1", limit=5)
        await rate_limit_cache.increment_and_check("client-1", limit=5)
        result = await rate_limit_cache.increment_and_check("client-1", limit=5)
        assert result.count == 3

    async def test_reports_exceeded_once_over_the_limit(
        self, rate_limit_cache: RateLimitCache
    ) -> None:
        for _ in range(3):
            await rate_limit_cache.increment_and_check("client-1", limit=3)
        result = await rate_limit_cache.increment_and_check("client-1", limit=3)
        assert result.count == 4
        assert result.exceeded is True

    async def test_different_identifiers_have_independent_counters(
        self, rate_limit_cache: RateLimitCache
    ) -> None:
        await rate_limit_cache.increment_and_check("client-1", limit=5)
        await rate_limit_cache.increment_and_check("client-1", limit=5)
        result = await rate_limit_cache.increment_and_check("client-2", limit=5)
        assert result.count == 1

    async def test_reset_clears_the_counter(self, rate_limit_cache: RateLimitCache) -> None:
        await rate_limit_cache.increment_and_check("client-1", limit=5)
        assert await rate_limit_cache.reset("client-1") is True
        result = await rate_limit_cache.increment_and_check("client-1", limit=5)
        assert result.count == 1

    async def test_reset_on_a_never_used_identifier_returns_false(
        self, rate_limit_cache: RateLimitCache
    ) -> None:
        assert await rate_limit_cache.reset("never-used") is False

    async def test_result_reports_the_window_seconds_used(
        self, rate_limit_cache: RateLimitCache
    ) -> None:
        result = await rate_limit_cache.increment_and_check("client-1", limit=5, window_seconds=30)
        assert result.window_seconds == 30
