"""Local-filesystem implementation of
``core.ports.model_artifact_store_port.ModelArtifactStorePort``.

Per that port's docstring: the only implementation Phase 12 ships, chosen
because it needs no additional infrastructure to run in dev/CI, and because
every method signature already treats ``artifact_uri`` as opaque -- an S3
(or any object-store) backend can be added later as a second
``ModelArtifactStorePort`` implementation, selected by
``config.modules.training.TrainingSettings.artifact_store_backend``, without
touching ``training/trainer.py`` or ``models/registry_client.py``, both of
which depend only on the port.
"""

from __future__ import annotations

from pathlib import Path

from core.ports.model_artifact_store_port import ModelArtifactStorePort
from shared.errors.exceptions import ModelRegistryError
from shared.logging.logger import get_logger

_logger = get_logger("models.artifact_store")

_URI_SCHEME = "file://"


class LocalFilesystemArtifactStore(ModelArtifactStorePort):
    """Stores each artifact as one file at
    ``{root}/{model_name}/{version}/model.bin``, returning a ``file://``
    URI. ``root`` is ``config.modules.training.TrainingSettings.artifact_store_dir``.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path_for(self, model_name: str, version: int) -> Path:
        return self._root / model_name / str(version) / "model.bin"

    def _path_from_uri(self, artifact_uri: str) -> Path:
        if not artifact_uri.startswith(_URI_SCHEME):
            raise ModelRegistryError(
                f"unrecognized artifact URI scheme: {artifact_uri!r} "
                f"(expected {_URI_SCHEME!r})"
            )
        return Path(artifact_uri[len(_URI_SCHEME) :])

    def save(self, model_name: str, version: int, artifact_bytes: bytes) -> str:
        path = self._path_for(model_name, version)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact_bytes)
        except OSError as exc:
            raise ModelRegistryError(
                f"failed to write model artifact: {exc}",
                context={"model_name": model_name, "version": version},
            ) from exc
        uri = f"{_URI_SCHEME}{path}"
        _logger.info(
            "model_artifact_saved",
            extra={
                "channel": "application",
                "model_name": model_name,
                "version": version,
                "artifact_uri": uri,
                "size_bytes": len(artifact_bytes),
            },
        )
        return uri

    def load(self, artifact_uri: str) -> bytes:
        path = self._path_from_uri(artifact_uri)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ModelRegistryError(
                f"failed to read model artifact: {exc}", context={"artifact_uri": artifact_uri}
            ) from exc

    def delete(self, artifact_uri: str) -> None:
        path = self._path_from_uri(artifact_uri)
        path.unlink(missing_ok=True)

    def exists(self, artifact_uri: str) -> bool:
        return self._path_from_uri(artifact_uri).is_file()


__all__ = ["LocalFilesystemArtifactStore"]
