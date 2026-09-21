"""Feast feature repository: entity/feature-view definitions and the
programmatic ``feature_store.yaml`` builder.

``feature_engineering/feature_store_client.py`` constructs a
``feast.FeatureStore`` directly from :func:`repo_builder.build_repo_config`
and calls ``store.apply(...)`` with the objects from
:mod:`feature_engineering.feast_repo.entities` and
:mod:`feature_engineering.feast_repo.feature_views` in Python, rather than
shelling out to the Feast CLI against a materialized ``feature_store.yaml`` +
``.py`` file pair on disk. This keeps the whole feature-store lifecycle
inside the same process/dependency-injection model as everything else in this
codebase (``core.container.Container``), with one exception: the offline
``FileSource`` parquet path and the registry's own SQLite file still need to
live on disk (see ``config.modules.feature_engineering.FeatureEngineeringSettings``),
since that's how Feast's file-based offline store and registry work.
"""

from __future__ import annotations

__all__: list[str] = []
