"""Prediction cache: caches AI model inference results keyed by model + input.

Avoids re-running inference for an identical (model, input) pair within its TTL
-- useful when the same feature vector is requested by more than one consumer
in a short window (e.g. a WebSocket fan-out and a REST poll both asking for the
current prediction for the same symbol).
"""

from __future__ import annotations

from typing import Any

from cache.cache_keys import NAMESPACE_PREDICTION
from cache.cache_manager import CacheManager


class PredictionCache:
    """Namespaced convenience wrapper over :class:`~cache.cache_manager.CacheManager`
    for model prediction results.

    Predictions are plain data (JSON-serializable) -- floats, dicts, lists --
    so this uses the default JSON serializer; a model whose raw output is not
    JSON-representable (e.g. a numpy array) should convert it to plain Python
    types before caching, or use :class:`~cache.cache_manager.CacheManager`
    directly with ``cache.serializers.pickle_serializer``.
    """

    def __init__(self, cache_manager: CacheManager, *, default_ttl_seconds: int) -> None:
        self._cache = cache_manager
        self._default_ttl_seconds = default_ttl_seconds

    def _key(self, model_name: str, model_version: str, input_hash: str) -> str:
        return f"{model_name}:{model_version}:{input_hash}"

    async def get(
        self, model_name: str, model_version: str, input_hash: str
    ) -> dict[str, Any] | None:
        """Return the cached prediction for this exact (model, version, input),
        or ``None`` on a cache miss."""
        return await self._cache.get(
            self._key(model_name, model_version, input_hash), namespace=NAMESPACE_PREDICTION
        )

    async def set(
        self,
        model_name: str,
        model_version: str,
        input_hash: str,
        prediction: dict[str, Any],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache ``prediction`` for this (model, version, input)."""
        await self._cache.set(
            self._key(model_name, model_version, input_hash),
            prediction,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds,
            namespace=NAMESPACE_PREDICTION,
        )

    async def invalidate(self, model_name: str, model_version: str, input_hash: str) -> bool:
        """Remove a specific cached prediction (e.g. after a model rollback)."""
        return await self._cache.delete(
            self._key(model_name, model_version, input_hash), namespace=NAMESPACE_PREDICTION
        )


__all__ = ["PredictionCache"]
