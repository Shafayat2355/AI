"""Redis-backed caching: connection pooling, namespaced keys, JSON/binary
serialization, named caches (prediction/market/session/rate-limit), a
distributed lock, and read-through/invalidation decorators.

Public API re-exported here so calling code writes ``from cache import
CacheManager`` instead of reaching into each submodule directly.
"""

from __future__ import annotations

from cache.cache_keys import (
    NAMESPACE_LOCK,
    NAMESPACE_MARKET,
    NAMESPACE_PREDICTION,
    NAMESPACE_RATE_LIMIT,
    NAMESPACE_SESSION,
    build_key,
)
from cache.cache_manager import CacheManager
from cache.decorators import cache_invalidate, cached
from cache.distributed_lock import DistributedLock, LockAcquisitionError
from cache.market_cache import MarketCache
from cache.prediction_cache import PredictionCache
from cache.rate_limit_cache import RateLimitCache, RateLimitResult
from cache.redis_client import RedisConnection, create_pool_from_settings
from cache.serializers import JSONSerializer, PickleSerializer, Serializer
from cache.serializers import json_serializer as json_serializer
from cache.serializers import pickle_serializer as pickle_serializer
from cache.session_cache import SessionCache

__all__ = [
    "NAMESPACE_LOCK",
    "NAMESPACE_MARKET",
    "NAMESPACE_PREDICTION",
    "NAMESPACE_RATE_LIMIT",
    "NAMESPACE_SESSION",
    "CacheManager",
    "DistributedLock",
    "JSONSerializer",
    "LockAcquisitionError",
    "MarketCache",
    "PickleSerializer",
    "PredictionCache",
    "RateLimitCache",
    "RateLimitResult",
    "RedisConnection",
    "Serializer",
    "SessionCache",
    "build_key",
    "cache_invalidate",
    "cached",
    "create_pool_from_settings",
    "json_serializer",
    "pickle_serializer",
]
