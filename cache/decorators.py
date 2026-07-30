"""Decorators for read-through caching and cache invalidation around async functions.

Both decorators need a way to obtain a :class:`~cache.cache_manager.CacheManager`
at call time (not decoration time, since the manager is constructed after
``Container`` startup, while decorators apply at import time) -- so both take a
zero-argument ``cache_manager_provider`` callable, matching
``core.container.get_container``'s own shape (a callable, not a value).
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from cache.cache_manager import CacheManager
from cache.serializers import Serializer, json_serializer
from shared.errors.exceptions import CacheError
from shared.logging.logger import get_logger

_logger = get_logger("cache.decorators")

CacheManagerProvider = Callable[[], CacheManager]
KeyBuilder = Callable[..., str]


def _default_key_builder(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Build a cache key from the function's qualified name and its arguments'
    ``repr`` (hashed, so an arbitrarily long/complex argument list still
    produces a short, fixed-length key segment)."""
    raw = f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{fn.__qualname__}:{digest}"


def cached(
    cache_manager_provider: CacheManagerProvider,
    *,
    namespace: str | None = None,
    ttl_seconds: int | None = None,
    serializer: Serializer = json_serializer,
    key_builder: KeyBuilder | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Read-through cache decorator for an ``async def`` function.

    On each call: build a cache key (from ``key_builder``, or the default
    argument-hash builder), check the cache, and only call the wrapped function
    on a miss -- caching its result before returning it. A
    :class:`~shared.errors.exceptions.CacheError` from the cache layer itself is
    logged and treated as a miss (the wrapped function still runs normally) --
    a Redis outage should degrade to "no caching", not break the decorated
    function's callers.

    Usage::

        @cached(get_cache_manager, namespace=NAMESPACE_PREDICTION, ttl_seconds=60)
        async def expensive_lookup(symbol: str) -> dict: ...
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_manager = cache_manager_provider()
            key = (
                key_builder(*args, **kwargs)
                if key_builder is not None
                else _default_key_builder(fn, args, kwargs)
            )

            try:
                cached_value = await cache_manager.get(
                    key, namespace=namespace, serializer=serializer
                )
            except CacheError:
                _logger.warning(
                    "cache_read_failed_falling_through",
                    extra={"channel": "application", "function": fn.__qualname__},
                    exc_info=True,
                )
                cached_value = None

            if cached_value is not None:
                return cached_value

            result = await fn(*args, **kwargs)

            try:
                await cache_manager.set(
                    key, result, ttl_seconds=ttl_seconds, namespace=namespace, serializer=serializer
                )
            except CacheError:
                _logger.warning(
                    "cache_write_failed",
                    extra={"channel": "application", "function": fn.__qualname__},
                    exc_info=True,
                )

            return result

        return wrapper

    return decorator


def cache_invalidate(
    cache_manager_provider: CacheManagerProvider,
    *,
    namespace: str | None = None,
    key_builder: KeyBuilder,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Invalidation decorator: after the wrapped function returns successfully,
    delete the cache entry ``key_builder(*args, **kwargs)`` would resolve to.

    Unlike :func:`cached`, ``key_builder`` is required here (there is no
    sensible default -- invalidation must target the exact key a prior
    :func:`cached` call used, which is a property of the *arguments*, not of
    this decorator call in isolation). If the wrapped function raises, no
    invalidation happens -- an unsuccessful mutation should not invalidate a
    cache entry that may still be accurate.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await fn(*args, **kwargs)
            cache_manager = cache_manager_provider()
            key = key_builder(*args, **kwargs)
            try:
                await cache_manager.delete(key, namespace=namespace)
            except CacheError:
                _logger.warning(
                    "cache_invalidation_failed",
                    extra={"channel": "application", "function": fn.__qualname__},
                    exc_info=True,
                )
            return result

        return wrapper

    return decorator


__all__ = ["CacheManagerProvider", "KeyBuilder", "cache_invalidate", "cached"]
