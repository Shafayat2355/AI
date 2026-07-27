"""Generic repository interface every concrete repository port extends.

``core/ports/order_repository_port.py``, ``portfolio_repository_port.py`` (and
their future siblings) are expected to subclass :class:`RepositoryPort` with their
own entity/id types rather than each re-declaring the same five methods, per the
hexagonal-architecture boundary in ``docs/PHASE1_ARCHITECTURE.md`` Sec 6: the
``core`` package only ever depends on abstractions, never on
``database/repositories/*``'s concrete SQLAlchemy implementations.

This module intentionally implements no trading-domain logic -- it is pure
bootstrap/scaffolding, in scope for Phase 6, so that later phases modeling
``core/domain`` entities have a base to subclass instead of inventing their own
per-entity CRUD contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class RepositoryPort[EntityT, IdT](ABC):
    """Minimal CRUD contract a persistence adapter must satisfy.

    Deliberately narrow (no query-building, no pagination cursor, no unit-of-work
    management beyond what the caller's session already provides) -- a concrete
    port that needs more than this composes additional domain-specific methods
    alongside these, rather than this base class growing to anticipate every
    future need.
    """

    @abstractmethod
    async def get(self, entity_id: IdT) -> EntityT | None:
        """Return the entity with ``entity_id``, or ``None`` if it does not exist."""

    @abstractmethod
    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[EntityT]:
        """Return up to ``limit`` entities, skipping the first ``offset``."""

    @abstractmethod
    async def add(self, entity: EntityT) -> EntityT:
        """Persist a new ``entity`` and return it (with any generated fields set)."""

    @abstractmethod
    async def update(self, entity: EntityT) -> EntityT:
        """Persist changes to an existing ``entity`` and return it."""

    @abstractmethod
    async def delete(self, entity_id: IdT) -> None:
        """Remove the entity with ``entity_id``. A no-op if it does not exist."""


__all__ = ["RepositoryPort"]
