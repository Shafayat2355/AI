"""Redis client factory with connection pooling shared by all consumers of Cache.

Mirrors ``database/connection.py``'s shape closely: one connection (pool) per
process, built once from ``config.settings.Settings``, exposed to
``core.container.Container`` for lifecycle management, with an opt-in retry
helper for startup connectivity verification and a never-raising health check
for a readiness probe.

Deliberately uses ``decode_responses=False`` regardless of the (unrelated)
``RedisSettings.decode_responses`` field some other consumer might read that
setting for -- ``cache/cache_manager.py`` supports both JSON and binary
(pickle) serialization, and Redis cannot know which a given value was encoded
with, so decoding is handled explicitly by the serializer, never by the client
itself. Decoding raw bytes as UTF-8 unconditionally would corrupt any binary
payload the moment it contained a byte sequence that is not valid UTF-8.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.client import Pipeline

from config.settings import Settings
from shared.logging.logger import get_logger
from shared.logging.retry import log_retries_async

_logger = get_logger("cache.redis_client")


def create_pool_from_settings(settings: Settings) -> ConnectionPool:
    """Build a new :class:`~redis.asyncio.ConnectionPool` from ``settings.redis``."""
    redis_settings = settings.redis
    dsn = (
        redis_settings.url.get_secret_value() if redis_settings.url else redis_settings.build_dsn()
    )
    return ConnectionPool.from_url(
        dsn,
        max_connections=redis_settings.max_connections,
        socket_timeout=redis_settings.socket_timeout_seconds,
        socket_connect_timeout=redis_settings.socket_connect_timeout_seconds,
        health_check_interval=redis_settings.health_check_interval_seconds,
        decode_responses=False,
    )


class RedisConnection:
    """Owns one Redis connection pool for the lifetime of a process.

    Constructed once by ``core.container.Container`` at startup and disposed once
    at shutdown -- never constructed per-request. Use :meth:`client` to get the
    shared :class:`~redis.asyncio.Redis` instance (itself just a thin, cheap
    handle onto the pool -- safe to use concurrently from many coroutines).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: ConnectionPool = create_pool_from_settings(settings)
        self._client: Redis = Redis(connection_pool=self._pool)

    @property
    def client(self) -> Redis:
        """The shared :class:`~redis.asyncio.Redis` client."""
        return self._client

    @asynccontextmanager
    async def pipeline(self, *, transaction: bool = True) -> AsyncIterator[Pipeline]:
        """Yield a Redis pipeline for batching several commands.

        ``transaction=True`` (the default) wraps the pipeline in ``MULTI``/``EXEC``
        so the batched commands apply atomically; pass ``False`` for a plain
        (non-atomic) batch when atomicity is not required.
        """
        async with self._client.pipeline(transaction=transaction) as pipe:
            yield pipe

    async def check_connection(self) -> bool:
        """Attempt a lightweight ``PING``; return whether it succeeded.

        Never raises -- a connectivity failure is an expected, reportable readiness
        result, not a process-level error, so it is caught and logged here rather
        than propagated. Mirrors
        ``database.connection.DatabaseConnection.check_connection`` exactly.
        """
        try:
            return bool(await self._client.ping())
        except Exception:
            _logger.warning(
                "redis_connectivity_check_failed",
                extra={"channel": "application"},
                exc_info=True,
            )
            return False

    async def connect_with_retry(
        self, *, max_attempts: int | None = None, backoff_seconds: float | None = None
    ) -> None:
        """Verify connectivity at startup, retrying with backoff before giving up.

        Opt-in -- not called automatically by ``core.container.Container.startup``,
        for the same reason ``database.connection.DatabaseConnection.connect_with_retry``
        is not (see ``docs/PHASE7_DATABASE_LAYER.md`` Sec 6): eager startup
        connectivity checks are a per-service decision, not a default this shared
        infrastructure layer should impose.

        Defaults come from ``RedisSettings.connect_retry_attempts``/
        ``connect_retry_backoff_seconds`` when not passed explicitly. Raises the
        underlying connection exception once attempts are exhausted -- unlike
        :meth:`check_connection`, which never raises.
        """
        resolved_max_attempts = max_attempts or self._settings.redis.connect_retry_attempts
        resolved_backoff = backoff_seconds or self._settings.redis.connect_retry_backoff_seconds

        @log_retries_async(
            max_attempts=resolved_max_attempts,
            backoff_seconds=resolved_backoff,
            exceptions=(Exception,),
            operation="cache.connect_with_retry",
        )
        async def _attempt() -> None:
            await self._client.ping()

        await _attempt()

    async def dispose(self) -> None:
        """Close every pooled connection. Called once, during graceful shutdown."""
        await self._client.aclose()
        await self._pool.disconnect()
        _logger.info("redis_pool_disposed", extra={"channel": "application"})


__all__ = ["RedisConnection", "create_pool_from_settings"]
