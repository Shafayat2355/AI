"""Distributed lock support, backed by redis-py's built-in ``SET NX PX`` lock.

A thin wrapper over ``redis.asyncio.lock.Lock`` (redis-py's own
token-based, safe-release distributed lock implementation) that adds this
platform's key-namespacing convention and structured logging -- it
deliberately does not reimplement lock acquisition/release itself.
"""

from __future__ import annotations

from types import TracebackType

from redis.asyncio.lock import Lock

from cache.cache_keys import NAMESPACE_LOCK, build_key
from cache.redis_client import RedisConnection
from config.settings import Settings
from shared.logging.logger import get_logger

_logger = get_logger("cache.distributed_lock")


class LockAcquisitionError(TimeoutError):
    """Raised by :meth:`DistributedLock.__aenter__` when the lock could not be
    acquired within ``blocking_timeout_seconds``."""


class DistributedLock:
    """A named, cross-process mutual-exclusion lock.

    Usage::

        lock = DistributedLock(redis_connection, settings, "reconcile:account-42")
        async with lock:
            ...  # only one process across the whole platform runs this at a time

    Or, for a non-blocking "try, don't wait" acquisition::

        if await lock.acquire(blocking=False):
            try:
                ...
            finally:
                await lock.release()
    """

    def __init__(
        self,
        redis_connection: RedisConnection,
        settings: Settings,
        name: str,
        *,
        timeout_seconds: float = 30.0,
        blocking_timeout_seconds: float | None = 10.0,
    ) -> None:
        key = build_key(name, namespace=NAMESPACE_LOCK, redis_settings=settings.redis)
        self._name = name
        self._lock: Lock = redis_connection.client.lock(
            key,
            timeout=timeout_seconds,
            blocking_timeout=blocking_timeout_seconds,
        )

    async def acquire(self, *, blocking: bool = True) -> bool:
        """Attempt to acquire the lock. Returns whether it was acquired.

        With ``blocking=True`` (the default), waits up to
        ``blocking_timeout_seconds`` before giving up and returning ``False``.
        """
        acquired = bool(await self._lock.acquire(blocking=blocking))
        if acquired:
            _logger.info(
                "distributed_lock_acquired",
                extra={"channel": "application", "lock_name": self._name},
            )
        return acquired

    async def release(self) -> None:
        """Release the lock. Safe to call only while this instance holds it."""
        await self._lock.release()
        _logger.info(
            "distributed_lock_released", extra={"channel": "application", "lock_name": self._name}
        )

    async def locked(self) -> bool:
        """Whether the lock is currently held by anyone (not necessarily this instance)."""
        return bool(await self._lock.locked())

    async def __aenter__(self) -> DistributedLock:
        if not await self.acquire(blocking=True):
            raise LockAcquisitionError(f"could not acquire lock {self._name!r} in time")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.release()


__all__ = ["DistributedLock", "LockAcquisitionError"]
