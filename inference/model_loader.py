"""Loads model artifacts from the MLOps registry into the serving process.

:class:`ModelLoader` resolves a model name (and optional pinned version) to a
fitted :class:`~models.model_definitions.lstm_price_model.BaselineDirectionModel`,
via the injected :class:`~core.ports.model_registry_port.ModelRegistryPort`
and :class:`~core.ports.model_artifact_store_port.ModelArtifactStorePort` --
never touching Postgres or the filesystem directly, matching every other
class in ``training``/``inference``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from core.domain.entities.model_version import ModelVersion
from core.ports.model_artifact_store_port import ModelArtifactStorePort
from core.ports.model_registry_port import ModelRegistryPort
from models.model_definitions.lstm_price_model import BaselineDirectionModel
from shared.errors.exceptions import ModelRegistryError
from shared.logging.logger import get_logger

_logger = get_logger("inference.model_loader")


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """A fitted model ready for inference, plus the version metadata
    ``inference/predictor.py`` includes in every prediction's response."""

    model: BaselineDirectionModel
    version: ModelVersion


class ModelLoader:
    """Resolves a model name/version to a :class:`LoadedModel`."""

    def __init__(
        self, model_registry: ModelRegistryPort, artifact_store: ModelArtifactStorePort
    ) -> None:
        self._model_registry = model_registry
        self._artifact_store = artifact_store

    async def load_production(self, model_name: str) -> LoadedModel:
        """Load whichever version of ``model_name`` is currently in
        production. This is what ``inference/predictor.py`` calls when the
        caller does not pin a specific version."""
        version = await self._model_registry.get_production_version(model_name)
        if version is None:
            raise ModelRegistryError(
                f"model {model_name!r} has no production version to load",
                context={"model_name": model_name},
            )
        return self._load_version(version)

    async def load_version(self, version_id: UUID) -> LoadedModel:
        """Load a specific version by its registry id, regardless of stage --
        used by evaluation/canary tooling that needs to run inference against
        a non-production candidate."""
        version = await self._model_registry.get_version(version_id)
        if version is None:
            raise ModelRegistryError(f"model version not found: {version_id}")
        return self._load_version(version)

    def _load_version(self, version: ModelVersion) -> LoadedModel:
        artifact_bytes = self._artifact_store.load(version.artifact_uri)
        model = BaselineDirectionModel.deserialize(artifact_bytes)
        _logger.info(
            "model_loaded",
            extra={
                "channel": "application",
                "model_name": version.model_name,
                "version": version.version,
                "stage": version.stage.value,
            },
        )
        return LoadedModel(model=model, version=version)


__all__ = ["LoadedModel", "ModelLoader"]
