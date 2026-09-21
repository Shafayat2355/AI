"""Abstract interface for online/offline feature retrieval.

Implemented by ``feature_engineering/feature_store_client.py`` (backed by
Feast, per Phase 11). Per the hexagonal dependency-flow rule already
established by ``core/ports/event_publisher_port.py`` and
``core/ports/base_repository.py``: ``core`` and anything built on it
(``training/``, ``inference/``) depend only on this abstraction, never on
``feast`` directly. The composition root (``core/container.py``) wires the
concrete Feast-backed client in.

Two retrieval shapes, matching Feast's own online/offline split and this
platform's two consumers of it:

* :meth:`FeatureStorePort.get_historical_features` -- point-in-time-correct
  features for a set of (entity, timestamp) rows, used by
  ``training/trainer.py`` to build a training dataset. Point-in-time
  correctness (never leaking a feature value computed *after* the label's
  timestamp) is the entire reason to go through Feast here rather than a
  plain SQL join.
* :meth:`FeatureStorePort.get_online_features` -- the latest feature values
  for a set of entities right now, used by ``inference/predictor.py`` at
  serving time. Both retrieval paths read the *same* feature definitions
  (``feature_engineering/feast_repo/feature_views.py``), which is what makes
  training/serving consistency a property of the feature store rather than
  something each caller must maintain by hand.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


class FeatureStorePort(ABC):
    """Contract a feature-store adapter must satisfy."""

    @abstractmethod
    def get_historical_features(
        self,
        entity_df: pd.DataFrame,
        feature_refs: list[str] | None = None,
    ) -> pd.DataFrame:
        """Return point-in-time-correct historical feature values.

        ``entity_df`` must contain the entity join key column(s) (e.g.
        ``symbol``) plus an ``event_timestamp`` column; the returned frame is
        ``entity_df`` with one column appended per entry in ``feature_refs``
        (``"<feature_view>:<feature>"``; ``None`` means every feature ref this
        platform defines), each row's value being the most recent value
        as-of that row's ``event_timestamp`` -- never a value computed later,
        which would leak future information into training.

        Must raise :class:`~shared.errors.exceptions.FeatureStoreError` if the
        retrieval itself fails (registry unreachable, offline store I/O
        error) -- never a bare/library-specific exception.
        """

    @abstractmethod
    def get_online_features(
        self,
        entity_rows: list[dict[str, Any]],
        feature_refs: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        """Return the latest feature values for each row in ``entity_rows``.

        ``entity_rows`` is a list of ``{"symbol": "BTCUSDT", ...}``-shaped
        dicts (one entity key mapping per row). ``feature_refs=None`` means
        every feature ref this platform defines. The result maps each
        requested feature name to a list of values, one per input row, in the
        same order -- this is Feast's own ``OnlineResponse.to_dict()`` shape,
        kept as-is rather than re-projected, since ``inference/predictor.py``
        is the only caller and already expects it.

        Must raise :class:`~shared.errors.exceptions.FeatureStoreError` on
        retrieval failure. A feature that is simply unmaterialized/unset for a
        given entity comes back as ``None`` in its slot, not an exception --
        that is an expected "cold start" outcome the caller decides how to
        handle, not an infrastructure failure.
        """

    @abstractmethod
    def materialize(self, start_date: datetime, end_date: datetime) -> None:
        """Push computed offline feature values for ``[start_date, end_date)``
        into the online store, so :meth:`get_online_features` can serve them.

        Must raise :class:`~shared.errors.exceptions.FeatureStoreError` if
        materialization fails.
        """

    @abstractmethod
    def apply(self) -> None:
        """(Re-)register this platform's feature/entity definitions with the
        feature store's registry. Idempotent -- safe to call on every process
        startup and from ``feature_engineering/offline_pipeline.py`` before a
        batch run, per Feast's own ``apply()`` semantics.
        """


__all__ = ["FeatureStorePort"]
