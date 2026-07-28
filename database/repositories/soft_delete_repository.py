"""Soft-delete-aware repository for models using :class:`database.mixins.SoftDeleteMixin`.

Extends ``database.repositories.base_repository.SQLAlchemyRepository`` (Phase 6,
unmodified) rather than changing its behavior -- a model that does *not* use
:class:`~database.mixins.SoftDeleteMixin` should keep the base class's plain hard
``delete()``; a model that does should use :class:`SoftDeleteRepository` instead.
Two distinct classes, not one class branching on ``hasattr``, keeps each
repository's delete semantics explicit.

Typing note: ``ModelT`` is bound to ``Base`` (matching the parent class's own
bound exactly -- that is the real, load-bearing constraint, since every model
this repository works with must be a mapped ``Base`` subclass). Python's type
system has no clean way to additionally express "...and also has
``SoftDeleteMixin``'s ``deleted_at`` column" as part of that same bound without
a ``Protocol`` that duplicates ``DeclarativeBase``'s own interface, which is not
worth the complexity here -- so the ``deleted_at`` accesses below go through
:class:`_HasDeletedAt`, a small local ``Protocol`` used only to type-check those
specific attribute accesses via ``cast``. A model used with this repository that
does not actually inherit :class:`~database.mixins.SoftDeleteMixin` will fail at
runtime (``AttributeError``), not at type-check time -- exactly like using any
other mixin-provided attribute without inheriting the mixin.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute

from database.base import Base
from database.repositories.base_repository import SQLAlchemyRepository


class _HasDeletedAt(Protocol):
    deleted_at: datetime | None


class SoftDeleteRepository[ModelT: Base, IdT](SQLAlchemyRepository[ModelT, IdT]):
    """CRUD repository whose ``delete`` sets ``deleted_at`` instead of removing the row.

    ``get``/``list`` exclude soft-deleted rows by default -- pass
    ``include_deleted=True`` for the (rarer) case of needing to see them, e.g. an
    admin "restore" screen or an audit report.
    """

    async def get(self, entity_id: IdT, *, include_deleted: bool = False) -> ModelT | None:
        entity = await super().get(entity_id)
        if entity is not None:
            deletable = cast(_HasDeletedAt, entity)
            if deletable.deleted_at is not None and not include_deleted:
                return None
        return entity

    async def list(
        self, *, limit: int = 100, offset: int = 0, include_deleted: bool = False
    ) -> Sequence[ModelT]:
        statement = select(self._model).limit(limit).offset(offset)
        if not include_deleted:
            deletable_column = cast(
                "InstrumentedAttribute[datetime | None]",
                getattr(self._model, "deleted_at"),  # noqa: B009 -- see class docstring
            )
            statement = statement.where(deletable_column.is_(None))
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def delete(self, entity_id: IdT) -> None:
        """Set ``deleted_at`` on the row rather than removing it.

        A no-op if the entity does not exist or is already soft-deleted --
        matches the base class's "no-op if it does not exist" contract for
        ``delete``, extended to also mean "already gone" for a soft-deletable
        model.
        """
        entity = await self.get(entity_id)
        if entity is None:
            return
        cast(_HasDeletedAt, entity).deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def restore(self, entity_id: IdT) -> ModelT | None:
        """Clear ``deleted_at``, undoing a prior soft delete. Returns the restored
        entity, or ``None`` if it does not exist (including if it was never
        deleted in the first place -- restoring a non-deleted row is a no-op that
        still returns it)."""
        entity = await self.get(entity_id, include_deleted=True)
        if entity is None:
            return None
        cast(_HasDeletedAt, entity).deleted_at = None
        await self._session.flush()
        return entity


__all__ = ["SoftDeleteRepository"]
