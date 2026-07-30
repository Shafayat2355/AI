"""Session cache: server-side state for a client session (e.g. a WebSocket
connection's subscriptions/reconnect state), keyed by session id.

See ``docs/PHASE1_ARCHITECTURE.md`` Sec 3.6, ``websocket/session_store.py``:
"persists connection/session state in Cache to support reconnect without data
loss" -- this module is the Cache-layer piece that fulfills that.
"""

from __future__ import annotations

from typing import Any

from cache.cache_keys import NAMESPACE_SESSION
from cache.cache_manager import CacheManager


class SessionCache:
    """Namespaced convenience wrapper over :class:`~cache.cache_manager.CacheManager`
    for per-session state."""

    def __init__(self, cache_manager: CacheManager, *, default_ttl_seconds: int) -> None:
        self._cache = cache_manager
        self._default_ttl_seconds = default_ttl_seconds

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Return the cached state for ``session_id``, or ``None`` if there is
        none (including if it expired -- a stale session should be treated the
        same as a nonexistent one, e.g. requiring re-authentication)."""
        return await self._cache.get(session_id, namespace=NAMESPACE_SESSION)

    async def set(
        self, session_id: str, state: dict[str, Any], *, ttl_seconds: int | None = None
    ) -> None:
        """Store ``state`` for ``session_id``, refreshing its TTL."""
        await self._cache.set(
            session_id,
            state,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds,
            namespace=NAMESPACE_SESSION,
        )

    async def touch(self, session_id: str, *, ttl_seconds: int | None = None) -> bool:
        """Extend ``session_id``'s TTL without changing its stored state (a
        "keep this session alive" heartbeat). Returns whether the session existed."""
        return await self._cache.touch(
            session_id,
            ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds,
            namespace=NAMESPACE_SESSION,
        )

    async def invalidate(self, session_id: str) -> bool:
        """End a session (e.g. on logout or disconnect), removing its state."""
        return await self._cache.delete(session_id, namespace=NAMESPACE_SESSION)


__all__ = ["SessionCache"]
