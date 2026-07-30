"""Unit tests for cache.cache_keys."""

from __future__ import annotations

from cache.cache_keys import (
    NAMESPACE_LOCK,
    NAMESPACE_MARKET,
    NAMESPACE_PREDICTION,
    NAMESPACE_RATE_LIMIT,
    NAMESPACE_SESSION,
    build_key,
)
from config.settings import Settings


class TestBuildKey:
    def test_includes_the_configured_prefix(self) -> None:
        settings = Settings()
        key = build_key("BTCUSDT", redis_settings=settings.redis)
        assert key.startswith("trading:")

    def test_includes_the_namespace_when_given(self) -> None:
        settings = Settings()
        key = build_key("BTCUSDT", namespace=NAMESPACE_MARKET, redis_settings=settings.redis)
        assert key == "trading:market:BTCUSDT"

    def test_omits_the_namespace_segment_when_not_given(self) -> None:
        settings = Settings()
        key = build_key("BTCUSDT", redis_settings=settings.redis)
        assert key == "trading:BTCUSDT"

    def test_joins_multiple_parts(self) -> None:
        settings = Settings()
        key = build_key(
            "model-a",
            "v1",
            "hash123",
            namespace=NAMESPACE_PREDICTION,
            redis_settings=settings.redis,
        )
        assert key == "trading:predictions:model-a:v1:hash123"

    def test_respects_a_non_default_prefix(self) -> None:
        from config.modules.redis import RedisSettings

        custom = RedisSettings(key_prefix="paper-env:")
        key = build_key("abc", namespace=NAMESPACE_SESSION, redis_settings=custom)
        assert key == "paper-env:sessions:abc"

    def test_every_namespace_constant_is_a_distinct_string(self) -> None:
        namespaces = {
            NAMESPACE_PREDICTION,
            NAMESPACE_MARKET,
            NAMESPACE_SESSION,
            NAMESPACE_RATE_LIMIT,
            NAMESPACE_LOCK,
        }
        assert len(namespaces) == 5

    def test_different_namespaces_never_collide_for_the_same_parts(self) -> None:
        settings = Settings()
        keys = {
            build_key("same-id", namespace=ns, redis_settings=settings.redis)
            for ns in (
                NAMESPACE_PREDICTION,
                NAMESPACE_MARKET,
                NAMESPACE_SESSION,
                NAMESPACE_RATE_LIMIT,
                NAMESPACE_LOCK,
            )
        }
        assert len(keys) == 5
