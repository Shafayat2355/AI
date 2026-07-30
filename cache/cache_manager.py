"""The cache manager: get/set/delete/TTL operations over namespaced keys, with
pluggable serialization.

``cache/prediction_cache.py``, ``market_cache.py``, ``session_cache.py``, and
``rate_limit_cache.py`` are all thin, purpose-specific wrappers around one
:class:`CacheManager` instance -- this module is where the actual Redis
commands live, so those four modules never talk to ``redis.asyncio`` directly.
"""

from __future__ import annotations

from typing import Any, cast

from cache.cache_keys import build_key
from cache.redis_client import RedisConnection
from cache.serializers import Serializer, json_serializer
from config.settings import Settings
from shared.errors.exceptions import CacheError
from shared.logging.logger import get_logger

_logger = get_logger("cache.cache_manager")


class CacheManager:
    """Namespaced get/set/delete/TTL operations over a shared
    :class:`~cache.redis_client.RedisConnection`.

    Every method accepts ``namespace`` (one of ``cache.cache_keys``'s
    ``NAMESPACE_*`` constants, or a caller-defined string) so unrelated
    consumers sharing one Redis instance never collide on key names -- see
    ``cache/cache_keys.py::build_key``.
    """

    def __init__(self, redis_connection: RedisConnection, settings: Settings) -> None:
        self._redis = redis_connection
        self._settings = settings

    def _key(self, key: str, *, namespace: str | None) -> str:
        return build_key(key, namespace=namespace, redis_settings=self._settings.redis)

    async def get(
        self, key: str, *, namespace: str | None = None, serializer: Serializer = json_serializer
    ) -> Any | None:
        """Return the cached value for ``key``, or ``None`` on a cache miss.

        A cache miss (key absent or expired) is a normal outcome, not an error --
        it returns ``None`` silently. A Redis-layer failure (connection lost,
        etc.) raises :class:`~shared.errors.exceptions.CacheError` instead of
        also returning ``None``, so callers can tell "definitely not cached"
        apart from "we don't know, Redis is unreachable".
        """
        full_key = self._key(key, namespace=namespace)
        try:
            raw = await self._redis.client.get(full_key)
        except Exception as exc:
            raise CacheError(
                f"failed to GET cache key {full_key!r}", context={"key": full_key}
            ) from exc
        if raw is None:
            return None
        return serializer.loads(cast(bytes, raw))

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
        namespace: str | None = None,
        serializer: Serializer = json_serializer,
    ) -> None:
        """Store ``value`` under ``key``, optionally expiring after ``ttl_seconds``.

        ``ttl_seconds=None`` means no expiry (the key persists until explicitly
        deleted) -- deliberately opt-in per call rather than a hidden global
        default, since "cache with no TTL" is a real and sometimes-intended
        choice, not an oversight.
        """
        full_key = self._key(key, namespace=namespace)
        payload = serializer.dumps(value)
        try:
            await self._redis.client.set(full_key, payload, ex=ttl_seconds)
        except Exception as exc:
            raise CacheError(
                f"failed to SET cache key {full_key!r}", context={"key": full_key}
            ) from exc

    async def delete(self, key: str, *, namespace: str | None = None) -> bool:
        """Delete ``key``. Returns whether a key was actually present and removed."""
        full_key = self._key(key, namespace=namespace)
        try:
            deleted_count = await self._redis.client.delete(full_key)
        except Exception as exc:
            raise CacheError(
                f"failed to DELETE cache key {full_key!r}", context={"key": full_key}
            ) from exc
        return bool(deleted_count)

    async def exists(self, key: str, *, namespace: str | None = None) -> bool:
        """Whether ``key`` is currently present (and not expired)."""
        full_key = self._key(key, namespace=namespace)
        try:
            return bool(await self._redis.client.exists(full_key))
        except Exception as exc:
            raise CacheError(
                f"failed to check existence of cache key {full_key!r}",
                context={"key": full_key},
            ) from exc

    async def get_ttl(self, key: str, *, namespace: str | None = None) -> int | None:
        """Remaining TTL in seconds, ``None`` if the key has no expiry set, or
        ``None`` if the key does not exist (Redis's ``-2``/``-1`` sentinels are
        both normalized to ``None`` here -- callers who need to tell them apart
        should call :meth:`exists` first)."""
        full_key = self._key(key, namespace=namespace)
        try:
            ttl = await self._redis.client.ttl(full_key)
        except Exception as exc:
            raise CacheError(
                f"failed to check TTL of cache key {full_key!r}", context={"key": full_key}
            ) from exc
        return ttl if ttl >= 0 else None

    async def touch(self, key: str, ttl_seconds: int, *, namespace: str | None = None) -> bool:
        """Reset ``key``'s TTL to ``ttl_seconds`` without changing its value.
        Returns whether the key existed."""
        full_key = self._key(key, namespace=namespace)
        try:
            return bool(await self._redis.client.expire(full_key, ttl_seconds))
        except Exception as exc:
            raise CacheError(
                f"failed to set TTL on cache key {full_key!r}", context={"key": full_key}
            ) from exc


__all__ = ["CacheManager"]
