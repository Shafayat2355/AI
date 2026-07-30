"""Unit tests for cache.cache_manager.CacheManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cache.cache_manager import CacheManager
from cache.serializers import pickle_serializer
from config.settings import Settings
from shared.errors.exceptions import CacheError
from tests.unit.cache.conftest import FakeRedisConnection


@pytest.fixture
def cache_manager(fake_redis_connection: FakeRedisConnection, settings: Settings) -> CacheManager:
    return CacheManager(fake_redis_connection, settings)  # type: ignore[arg-type]


class TestGetSet:
    async def test_get_returns_none_for_a_missing_key(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.get("missing") is None

    async def test_set_then_get_round_trips_a_json_value(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("k", {"a": 1, "b": [1, 2, 3]})
        assert await cache_manager.get("k") == {"a": 1, "b": [1, 2, 3]}

    async def test_set_then_get_round_trips_a_pickled_value(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("k", {"a": 1}, serializer=pickle_serializer)
        assert await cache_manager.get("k", serializer=pickle_serializer) == {"a": 1}

    async def test_different_namespaces_do_not_collide_on_the_same_key(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("shared-key", "value-a", namespace="ns-a")
        await cache_manager.set("shared-key", "value-b", namespace="ns-b")
        assert await cache_manager.get("shared-key", namespace="ns-a") == "value-a"
        assert await cache_manager.get("shared-key", namespace="ns-b") == "value-b"

    async def test_overwriting_a_key_replaces_its_value(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("k", "first")
        await cache_manager.set("k", "second")
        assert await cache_manager.get("k") == "second"


class TestTTL:
    async def test_set_with_ttl_makes_the_key_expire(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("k", "v", ttl_seconds=100)
        ttl = await cache_manager.get_ttl("k")
        assert ttl is not None
        assert 0 < ttl <= 100

    async def test_set_without_ttl_means_no_expiry(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("k", "v")
        assert await cache_manager.get_ttl("k") is None

    async def test_get_ttl_for_a_missing_key_is_none(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.get_ttl("missing") is None

    async def test_touch_updates_the_ttl_of_an_existing_key(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("k", "v", ttl_seconds=10)
        assert await cache_manager.touch("k", 999) is True
        ttl = await cache_manager.get_ttl("k")
        assert ttl is not None
        assert ttl > 10

    async def test_touch_on_a_missing_key_returns_false(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.touch("missing", 100) is False


class TestExistsAndDelete:
    async def test_exists_is_false_for_a_missing_key(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.exists("missing") is False

    async def test_exists_is_true_after_set(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("k", "v")
        assert await cache_manager.exists("k") is True

    async def test_delete_removes_the_key_and_reports_it_existed(
        self, cache_manager: CacheManager
    ) -> None:
        await cache_manager.set("k", "v")
        assert await cache_manager.delete("k") is True
        assert await cache_manager.exists("k") is False

    async def test_delete_on_a_missing_key_returns_false(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.delete("missing") is False


class TestCacheErrorOnRedisFailure:
    async def test_get_raises_cache_error_on_a_connection_failure(
        self, cache_manager: CacheManager
    ) -> None:
        with (
            patch.object(
                cache_manager._redis.client, "get", AsyncMock(side_effect=ConnectionError("down"))
            ),
            pytest.raises(CacheError),
        ):
            await cache_manager.get("k")

    async def test_set_raises_cache_error_on_a_connection_failure(
        self, cache_manager: CacheManager
    ) -> None:
        with (
            patch.object(
                cache_manager._redis.client, "set", AsyncMock(side_effect=ConnectionError("down"))
            ),
            pytest.raises(CacheError),
        ):
            await cache_manager.set("k", "v")

    async def test_cache_error_carries_the_offending_key_as_context(
        self, cache_manager: CacheManager
    ) -> None:
        with patch.object(
            cache_manager._redis.client, "get", AsyncMock(side_effect=ConnectionError("down"))
        ):
            try:
                await cache_manager.get("my-key", namespace="ns")
            except CacheError as exc:
                assert "my-key" in exc.context["key"]
            else:
                pytest.fail("expected CacheError")
