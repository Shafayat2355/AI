"""Build a :class:`feast.repo_config.RepoConfig` from this platform's own
:class:`~config.settings.Settings`, instead of a checked-in
``feature_store.yaml``.

Per this package's ``__init__.py`` docstring: every value Feast needs (registry
location, offline/online store backend) is already expressed in
``config.modules.feature_engineering.FeatureEngineeringSettings`` and
``config.modules.redis.RedisSettings`` -- re-expressing them a second time in
a YAML file on disk would duplicate configuration this codebase otherwise
keeps in one place. The Redis connection this builds reuses the *same* Redis
instance ``cache/redis_client.py`` connects to (Phase 8) -- Feast's online
store is namespaced by its own ``project`` name, so it does not collide with
this platform's other cache namespaces (``cache/cache_keys.py``).
"""

from __future__ import annotations

from pathlib import Path

from feast.repo_config import RepoConfig

from config.settings import Settings


def _redis_connection_string(settings: Settings) -> str:
    redis = settings.redis
    parts = [f"{redis.host}:{redis.port}", f"db={redis.db}"]
    if redis.password is not None:
        parts.append(f"password={redis.password.get_secret_value()}")
    if redis.use_tls:
        parts.append("ssl=true")
    return ",".join(parts)


def build_repo_config(settings: Settings) -> RepoConfig:
    """Build the :class:`RepoConfig` this platform's single Feast project
    uses, entirely from ``settings.feature_engineering``/``settings.redis`` --
    no YAML file involved.

    ``online_store`` is selected by
    ``FeatureEngineeringSettings.online_store_backend`` (default ``"redis"``,
    reusing Phase 8's Redis) -- ``"sqlite"`` is also supported for tests/local
    dev that do not have Redis running, matching
    ``config.modules.database.DatabaseSettings``'s own sqlite-for-tests
    convention.
    """
    fe = settings.feature_engineering
    offline_root = Path(fe.offline_store_path)
    offline_root.mkdir(parents=True, exist_ok=True)
    registry_path = offline_root / "registry.db"

    if fe.online_store_backend == "redis":
        online_store: dict[str, object] = {
            "type": "redis",
            "connection_string": _redis_connection_string(settings),
        }
    elif fe.online_store_backend == "sqlite":
        online_store = {"type": "sqlite", "path": str(offline_root / "online.db")}
    else:
        raise ValueError(
            f"unsupported FeatureEngineeringSettings.online_store_backend: "
            f"{fe.online_store_backend!r} (expected 'redis' or 'sqlite')"
        )

    return RepoConfig(
        project=fe.feast_project_name,
        provider="local",
        registry=str(registry_path),
        online_store=online_store,
        offline_store={"type": "file"},
        entity_key_serialization_version=3,
    )


__all__ = ["build_repo_config"]
