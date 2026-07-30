"""Unit tests for cache.decorators."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cache.cache_manager import CacheManager
from cache.decorators import cache_invalidate, cached
from config.settings import Settings
from shared.errors.exceptions import CacheError
from tests.unit.cache.conftest import FakeRedisConnection


@pytest.fixture
def cache_manager(fake_redis_connection: FakeRedisConnection, settings: Settings) -> CacheManager:
    return CacheManager(fake_redis_connection, settings)  # type: ignore[arg-type]


class TestCachedDecorator:
    async def test_calls_the_wrapped_function_on_a_miss(self, cache_manager: CacheManager) -> None:
        calls = {"count": 0}

        @cached(lambda: cache_manager)
        async def compute(x: int) -> int:
            calls["count"] += 1
            return x * 2

        assert await compute(5) == 10
        assert calls["count"] == 1

    async def test_second_call_with_the_same_args_hits_the_cache(
        self, cache_manager: CacheManager
    ) -> None:
        calls = {"count": 0}

        @cached(lambda: cache_manager)
        async def compute(x: int) -> int:
            calls["count"] += 1
            return x * 2

        assert await compute(5) == 10
        assert await compute(5) == 10
        assert calls["count"] == 1  # the wrapped function only ran once

    async def test_different_args_produce_different_cache_entries(
        self, cache_manager: CacheManager
    ) -> None:
        calls = {"count": 0}

        @cached(lambda: cache_manager)
        async def compute(x: int) -> int:
            calls["count"] += 1
            return x * 2

        assert await compute(5) == 10
        assert await compute(6) == 12
        assert calls["count"] == 2

    async def test_custom_key_builder_is_used_when_given(self, cache_manager: CacheManager) -> None:
        calls = {"count": 0}

        @cached(lambda: cache_manager, key_builder=lambda x: f"fixed-key-{x // 10}")
        async def compute(x: int) -> int:
            calls["count"] += 1
            return x

        # 5 and 7 both map to "fixed-key-0" under this key_builder -- second
        # call should be a cache hit despite the different argument.
        assert await compute(5) == 5
        assert await compute(7) == 5  # cached value from the first call
        assert calls["count"] == 1

    async def test_falls_through_to_the_function_on_a_cache_read_failure(
        self, cache_manager: CacheManager
    ) -> None:
        calls = {"count": 0}

        @cached(lambda: cache_manager)
        async def compute(x: int) -> int:
            calls["count"] += 1
            return x * 2

        with patch.object(cache_manager, "get", AsyncMock(side_effect=CacheError("down"))):
            assert await compute(5) == 10
        assert calls["count"] == 1

    async def test_respects_the_configured_ttl(self, cache_manager: CacheManager) -> None:
        async def _compute(x: int) -> int:
            return x

        compute = cached(lambda: cache_manager, ttl_seconds=42)(_compute)

        await compute(1)
        # Inspect the TTL of whatever key was actually written, via the cache
        # manager's own get_ttl -- proves the ttl_seconds kwarg reached CacheManager.set.
        from cache.decorators import _default_key_builder

        key = _default_key_builder(_compute, (1,), {})
        ttl = await cache_manager.get_ttl(key)
        assert ttl is not None
        assert 0 < ttl <= 42


class TestCacheInvalidateDecorator:
    async def test_deletes_the_targeted_key_after_a_successful_call(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("account-42", {"balance": 100})

        @cache_invalidate(
            lambda: cache_manager, key_builder=lambda account_id, new_balance: account_id
        )
        async def update_balance(account_id: str, new_balance: int) -> None:
            return None

        await update_balance("account-42", 200)
        assert await cache_manager.get("account-42") is None

    async def test_does_not_invalidate_if_the_function_raises(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("account-42", {"balance": 100})

        @cache_invalidate(lambda: cache_manager, key_builder=lambda account_id: account_id)
        async def update_balance(account_id: str) -> None:
            raise RuntimeError("update failed")

        with pytest.raises(RuntimeError):
            await update_balance("account-42")
        assert await cache_manager.get("account-42") == {"balance": 100}

    async def test_returns_the_wrapped_functions_result(self, cache_manager: CacheManager) -> None:
        @cache_invalidate(lambda: cache_manager, key_builder=lambda x: "k")
        async def compute(x: int) -> int:
            return x * 2

        assert await compute(5) == 10
