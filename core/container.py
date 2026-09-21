"""Application-lifetime dependency-injection container.

``config/di.py`` already provides fine-grained, per-request-safe providers for
individual settings modules (``get_redis_settings``, etc.) -- those stay as-is,
since a settings object is cheap to resolve on every call. ``Container`` exists one
level up: it owns the handful of resources that are expensive to create, must be
created exactly once per process, and must be explicitly disposed on shutdown --
as of Phase 8: the database engine/session factory in
``database.connection.DatabaseConnection`` and the Redis connection pool in
``cache.redis_client.RedisConnection``/``cache.cache_manager.CacheManager``.
A composition root (``app/*_service/main.py``) builds one ``Container`` in its
FastAPI ``lifespan`` handler, stores it on ``app.state.container``, and disposes it
on shutdown via :meth:`Container.shutdown`.

This module intentionally owns process-lifetime *infrastructure* only -- it does
not construct domain services or repositories (``core/use_cases/*``,
``database/repositories/*``), since none are implemented yet as of Phase 6. Later
phases that add a concrete use case are expected to add a corresponding
``Container`` property/factory method here rather than each service wiring its own
dependencies ad hoc.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from cache.cache_manager import CacheManager
from cache.redis_client import RedisConnection
from config.settings import Settings, get_settings
from core.ports.feature_store_port import FeatureStorePort
from core.ports.model_artifact_store_port import ModelArtifactStorePort
from database.connection import DatabaseConnection
from shared.enums import ServiceLifecycleState
from shared.logging.logger import get_logger
from shared.messaging.kafka_producer import KafkaProducer

_logger = get_logger("core.container")


class Container:
    """Owns and lazily initializes this process's expensive, long-lived resources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        self.state: ServiceLifecycleState = ServiceLifecycleState.STARTING
        self._db_connection: DatabaseConnection | None = None
        self._redis_connection: RedisConnection | None = None
        self._cache_manager: CacheManager | None = None
        self._kafka_producer: KafkaProducer | None = None
        self._feature_store: FeatureStorePort | None = None
        self._artifact_store: ModelArtifactStorePort | None = None

    @property
    def db(self) -> DatabaseConnection:
        """The process's single :class:`DatabaseConnection`, created on first access."""
        if self._db_connection is None:
            self._db_connection = DatabaseConnection(self.settings)
        return self._db_connection

    @property
    def redis(self) -> RedisConnection:
        """The process's single :class:`RedisConnection`, created on first access."""
        if self._redis_connection is None:
            self._redis_connection = RedisConnection(self.settings)
        return self._redis_connection

    @property
    def cache(self) -> CacheManager:
        """The process's single :class:`CacheManager`, created on first access.

        Built from :attr:`redis` (so accessing this also lazily creates the
        Redis connection pool if nothing has yet) -- mirrors :attr:`db`'s exact
        lazy-construction shape from Phase 6/7.
        """
        if self._cache_manager is None:
            self._cache_manager = CacheManager(self.redis, self.settings)
        return self._cache_manager

    @property
    def kafka_producer(self) -> KafkaProducer:
        """The process's single :class:`KafkaProducer`, created on first access.

        Mirrors :attr:`db`/:attr:`redis`'s exact lazy-construction shape.
        Unlike those two, the underlying ``AIOKafkaProducer`` is not connected
        yet at this point -- :class:`KafkaProducer` itself lazily starts on
        first :meth:`~shared.messaging.kafka_producer.KafkaProducer.publish`
        call (see that class's docstring for why).
        """
        if self._kafka_producer is None:
            self._kafka_producer = KafkaProducer(self.settings)
        return self._kafka_producer

    @property
    def feature_store(self) -> FeatureStorePort:
        """The process's single Feast-backed :class:`FeatureStorePort`, created
        on first access (Phase 11).

        Mirrors :attr:`db`/:attr:`redis`/:attr:`kafka_producer`'s exact lazy
        construction shape. Callers (``training/trainer.py``,
        ``inference/predictor.py``) depend on the
        ``core.ports.feature_store_port.FeatureStorePort`` return type, not the
        concrete Feast client, per that port's own hexagonal-boundary docstring.
        """
        if self._feature_store is None:
            from feature_engineering.feature_store_client import FeastFeatureStoreClient

            self._feature_store = FeastFeatureStoreClient(self.settings)
        return self._feature_store

    @property
    def artifact_store(self) -> ModelArtifactStorePort:
        """The process's single :class:`ModelArtifactStorePort`, created on
        first access (Phase 12). Unlike ``models.registry_client.PostgresModelRegistry``'s
        per-session construction pattern (it takes a request-scoped
        ``AsyncSession``), an artifact store has no request-scoped state to
        isolate -- it is a thin, stateless wrapper over a filesystem root --
        so it is cached here like :attr:`feature_store`.
        """
        if self._artifact_store is None:
            from models.artifact_store import LocalFilesystemArtifactStore

            self._artifact_store = LocalFilesystemArtifactStore(
                self.settings.training.artifact_store_dir
            )
        return self._artifact_store

    async def startup(self) -> None:
        """Mark the container ready. Idempotent; safe to call once from ``lifespan``.

        Resources themselves (e.g. :attr:`db`) are created lazily on first access
        rather than here, so a service that never touches the database never pays
        for an engine it does not use.
        """
        self.state = ServiceLifecycleState.READY
        _logger.info("container_started", extra={"channel": "application"})

    async def shutdown(self) -> None:
        """Release every resource this container created. Idempotent."""
        self.state = ServiceLifecycleState.DRAINING
        if self._db_connection is not None:
            await self._db_connection.dispose()
            self._db_connection = None
        if self._redis_connection is not None:
            await self._redis_connection.dispose()
            self._redis_connection = None
            self._cache_manager = None
        if self._kafka_producer is not None:
            await self._kafka_producer.dispose()
            self._kafka_producer = None
        self._feature_store = None
        self._artifact_store = None
        self.state = ServiceLifecycleState.STOPPED
        _logger.info("container_stopped", extra={"channel": "application"})


_container: Container | None = None


def get_container(settings: Settings | None = None) -> Container:
    """Return the process-wide :class:`Container` singleton, creating it if needed.

    Mirrors ``config.factory.SettingsFactory.create``'s caching shape so
    composition roots and FastAPI ``Depends()`` providers share one instance.
    """
    global _container
    if _container is None:
        _container = Container(settings)
    return _container


def reset_container() -> None:
    """Drop the cached :class:`Container` singleton.

    Does **not** dispose its resources -- callers that need a clean shutdown call
    :meth:`Container.shutdown` first (as ``app/api_service/main.py``'s ``lifespan``
    does). Intended for test teardown, mirroring
    ``config.factory.SettingsFactory.clear_cache``.
    """
    global _container
    _container = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a request-scoped :class:`AsyncSession`.

    Usage: ``session: AsyncSession = Depends(get_db_session)``.
    """
    container = get_container()
    async for session in container.db.session():
        yield session


def get_cache_manager() -> CacheManager:
    """FastAPI dependency: return the process's shared :class:`CacheManager`.

    Usage: ``cache: CacheManager = Depends(get_cache_manager)``. Unlike
    :func:`get_db_session`, this returns the manager directly rather than a
    request-scoped resource -- ``CacheManager`` (like ``Redis`` itself) is a
    cheap, concurrency-safe handle onto the shared connection pool, not
    something that needs a fresh instance per request.
    """
    return get_container().cache


def get_kafka_producer() -> KafkaProducer:
    """FastAPI dependency: return the process's shared :class:`KafkaProducer`.

    Usage: ``producer: KafkaProducer = Depends(get_kafka_producer)``. Returns the
    wrapper directly rather than a request-scoped resource, for the same reason
    :func:`get_cache_manager` does -- a concurrency-safe handle onto one shared
    connection, not something that needs a fresh instance per request.
    """
    return get_container().kafka_producer


def get_feature_store() -> FeatureStorePort:
    """FastAPI dependency: return the process's shared :class:`FeatureStorePort`.

    Usage: ``feature_store: FeatureStorePort = Depends(get_feature_store)``.
    """
    return get_container().feature_store


def get_artifact_store() -> ModelArtifactStorePort:
    """FastAPI dependency: return the process's shared :class:`ModelArtifactStorePort`.

    Usage: ``artifact_store: ModelArtifactStorePort = Depends(get_artifact_store)``.
    """
    return get_container().artifact_store


__all__ = [
    "Container",
    "get_artifact_store",
    "get_cache_manager",
    "get_container",
    "get_db_session",
    "get_feature_store",
    "get_kafka_producer",
    "reset_container",
]
