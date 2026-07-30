"""Centralized cache key naming conventions to avoid key collisions across services.

Every cache key in the platform is built through :func:`build_key` rather than
hand-assembled with ad hoc string formatting, so the prefix/namespace/separator
convention lives in exactly one place. Namespace constants below are the
canonical name for each of Phase 8's four named caches
(``cache/prediction_cache.py``, ``market_cache.py``, ``session_cache.py``,
``rate_limit_cache.py``) plus ``NAMESPACE_LOCK`` for
``cache/distributed_lock.py`` -- pass one of these as ``namespace`` rather than
inventing a new string per call site.
"""

from __future__ import annotations

from config.modules.redis import RedisSettings

#: Canonical namespace for each Phase 8 named cache / the distributed lock helper.
NAMESPACE_PREDICTION = "predictions"
NAMESPACE_MARKET = "market"
NAMESPACE_SESSION = "sessions"
NAMESPACE_RATE_LIMIT = "rate_limits"
NAMESPACE_LOCK = "locks"

_SEPARATOR = ":"


def build_key(*parts: str, namespace: str | None = None, redis_settings: RedisSettings) -> str:
    """Build a namespaced, prefixed cache key from ``parts``.

    ``redis_settings.key_prefix`` (default ``"trading:"``) always comes first,
    then ``namespace`` (one of the ``NAMESPACE_*`` constants above) if given,
    then every part in ``parts`` joined with ``:``. Empty parts are dropped
    rather than producing a doubled separator.

    Example: ``build_key("BTCUSDT", "1m", namespace=NAMESPACE_MARKET,
    redis_settings=settings.redis)`` -> ``"trading:market:BTCUSDT:1m"``.
    """
    prefix = redis_settings.key_prefix.rstrip(_SEPARATOR)
    segments = [prefix, namespace, *parts]
    return _SEPARATOR.join(segment for segment in segments if segment)


__all__ = [
    "NAMESPACE_LOCK",
    "NAMESPACE_MARKET",
    "NAMESPACE_PREDICTION",
    "NAMESPACE_RATE_LIMIT",
    "NAMESPACE_SESSION",
    "build_key",
]
