"""Market cache: short-TTL cache for the latest quote/tick per symbol.

Not a substitute for ``database.datasets``/a real time-series store -- this is
purely a "what's the latest price right now" read cache in front of the
``market_data``/``websocket`` pipeline (see
``docs/PHASE1_ARCHITECTURE.md`` Sec 3.5-3.6), with a deliberately short default
TTL (``RedisSettings.market_cache_ttl_seconds``, default 5s) since market data
goes stale within seconds.
"""

from __future__ import annotations

from typing import Any

from cache.cache_keys import NAMESPACE_MARKET
from cache.cache_manager import CacheManager


class MarketCache:
    """Namespaced convenience wrapper over :class:`~cache.cache_manager.CacheManager`
    for the latest tick/quote per symbol."""

    def __init__(self, cache_manager: CacheManager, *, default_ttl_seconds: int) -> None:
        self._cache = cache_manager
        self._default_ttl_seconds = default_ttl_seconds

    async def get_latest_tick(self, symbol: str) -> dict[str, Any] | None:
        """Return the most recently cached tick for ``symbol``, or ``None`` if
        none is cached (or it expired)."""
        return await self._cache.get(symbol, namespace=NAMESPACE_MARKET)

    async def set_latest_tick(
        self, symbol: str, tick: dict[str, Any], *, ttl_seconds: int | None = None
    ) -> None:
        """Cache ``tick`` as the latest known tick for ``symbol``."""
        await self._cache.set(
            symbol,
            tick,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds,
            namespace=NAMESPACE_MARKET,
        )

    async def invalidate(self, symbol: str) -> bool:
        """Remove the cached tick for ``symbol``."""
        return await self._cache.delete(symbol, namespace=NAMESPACE_MARKET)


__all__ = ["MarketCache"]
