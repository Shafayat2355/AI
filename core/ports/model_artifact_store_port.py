"""Abstract interface for storing/retrieving serialized model artifacts.

Implemented by ``models/artifact_store.py`` (local filesystem backend, per
Phase 12). Deliberately separate from ``core/ports/model_registry_port.py`` --
the registry owns *metadata* (versions, stages, evaluation results), while
this port owns *bytes* (the serialized model file itself); ``training/trainer.py``
stores an artifact through this port first, then registers its resulting
``artifact_uri`` with the registry, mirroring how a real object-store-backed
MLflow/S3 setup separates the two concerns.

Designed so a future S3 backend can be added by implementing this same port
(per Phase 12's "Design the abstraction so that object storage such as S3 can
be added later without changing model-management interfaces" requirement) --
no method here assumes a local filesystem path is meaningful to the caller;
``artifact_uri`` is opaque outside this port's own implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ModelArtifactStorePort(ABC):
    """Contract a model-artifact storage adapter must satisfy."""

    @abstractmethod
    def save(self, model_name: str, version: int, artifact_bytes: bytes) -> str:
        """Persist ``artifact_bytes`` for ``model_name``/``version`` and
        return an opaque ``artifact_uri`` identifying it for later
        :meth:`load` calls.

        Must raise :class:`~shared.errors.exceptions.ModelRegistryError` if
        the artifact cannot be written.
        """

    @abstractmethod
    def load(self, artifact_uri: str) -> bytes:
        """Return the raw bytes previously stored at ``artifact_uri``.

        Must raise :class:`~shared.errors.exceptions.ModelRegistryError` if
        ``artifact_uri`` does not exist or cannot be read.
        """

    @abstractmethod
    def delete(self, artifact_uri: str) -> None:
        """Remove the artifact at ``artifact_uri``. Idempotent -- deleting an
        already-absent artifact is not an error, matching
        ``cache/redis_client.py``'s own idempotent-delete convention."""

    @abstractmethod
    def exists(self, artifact_uri: str) -> bool:
        """Whether an artifact is currently stored at ``artifact_uri``."""


__all__ = ["ModelArtifactStorePort"]
