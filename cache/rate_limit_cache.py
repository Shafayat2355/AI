"""Rate limit cache: a fixed-window request counter backed by Redis ``INCR``.

Not wired into ``api/middleware/rate_limit_middleware.py`` in this phase --
see ``docs/PHASE8_REDIS_INFRASTRUCTURE.md`` for why that wiring decision is
left for explicit approval, mirroring how Phase 7 left
``DatabaseConnection.connect_with_retry`` unwired from ``Container.startup``.
"""

from __future__ import annotations

from dataclasses import dataclass

from cache.cache_keys import NAMESPACE_RATE_LIMIT, build_key
from cache.redis_client import RedisConnection
from config.settings import Settings
from shared.errors.exceptions import CacheError


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of one :meth:`RateLimitCache.increment_and_check` call."""

    count: int
    limit: int
    exceeded: bool
    window_seconds: int


class RateLimitCache:
    """Fixed-window rate limiter: counts requests for ``identifier`` within a
    rolling ``window_seconds`` bucket, backed by an atomic ``INCR`` +
    conditional ``EXPIRE``.

    Uses ``RedisConnection``/raw Redis commands directly rather than
    :class:`~cache.cache_manager.CacheManager` -- a rate-limit counter is a
    plain Redis integer (``INCR``'s native semantics), not a serialized value,
    so the JSON/pickle serialization layer does not apply here.
    """

    def __init__(
        self, redis_connection: RedisConnection, settings: Settings, *, default_window_seconds: int
    ) -> None:
        self._redis = redis_connection
        self._settings = settings
        self._default_window_seconds = default_window_seconds

    def _key(self, identifier: str) -> str:
        return build_key(
            identifier, namespace=NAMESPACE_RATE_LIMIT, redis_settings=self._settings.redis
        )

    async def increment_and_check(
        self, identifier: str, *, limit: int, window_seconds: int | None = None
    ) -> RateLimitResult:
        """Increment ``identifier``'s counter and report whether ``limit`` is exceeded.

        The first increment in a fresh window sets that window's expiry via
        ``EXPIRE ... NX`` (only if no expiry is already set) immediately after
        the ``INCR`` -- a small window exists between the two commands where a
        process crash could leave a key without an expiry; accepted as a
        bounded, self-healing edge case (the key still gets an expiry on the
        very next request that hits it) rather than paying for a Lua script for
        full atomicity, which this simple a limiter does not need. A precise,
        contended-safe rate limiter (e.g. a Lua-scripted sliding-window
        algorithm) is a valid future enhancement -- not implemented here to keep
        this phase's scope to what mixing INCR + EXPIRE self-consistently
        provides.
        """
        resolved_window = window_seconds or self._default_window_seconds
        key = self._key(identifier)
        try:
            count = await self._redis.client.incr(key)
            if count == 1:
                await self._redis.client.expire(key, resolved_window, nx=True)
        except Exception as exc:
            raise CacheError(
                f"failed to increment rate limit counter {key!r}", context={"key": key}
            ) from exc
        return RateLimitResult(
            count=count, limit=limit, exceeded=count > limit, window_seconds=resolved_window
        )

    async def reset(self, identifier: str) -> bool:
        """Clear ``identifier``'s counter early (e.g. an admin override)."""
        key = self._key(identifier)
        try:
            return bool(await self._redis.client.delete(key))
        except Exception as exc:
            raise CacheError(
                f"failed to reset rate limit counter {key!r}", context={"key": key}
            ) from exc


__all__ = ["RateLimitCache", "RateLimitResult"]
