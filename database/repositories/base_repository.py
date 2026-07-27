"""Generic SQLAlchemy-backed implementation of ``core.ports.base_repository.RepositoryPort``.

Concrete repositories under this package (``order_repository.py``,
``account_repository.py``, ``portfolio_repository.py``) are expected to subclass
:class:`SQLAlchemyRepository` with their own mapped model once implemented in a
later phase, rather than hand-rolling the same session/select/flush boilerplate
for every entity.

This module is pure bootstrap/scaffolding (Phase 6) -- it maps no concrete table
and contains no trading-domain logic.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.ports.base_repository import RepositoryPort
from database.base import Base


class SQLAlchemyRepository[ModelT: Base, IdT](RepositoryPort[ModelT, IdT]):
    """Generic async CRUD repository for one mapped ``model`` type.

    Takes an already-open :class:`AsyncSession` (request-scoped, provided by
    ``core.container.get_db_session``) rather than owning its own session or
    engine -- keeps transaction boundaries with the caller, which may need to
    coordinate several repositories in one unit of work.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get(self, entity_id: IdT) -> ModelT | None:
        return await self._session.get(self._model, entity_id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        statement = select(self._model).limit(limit).offset(offset)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def add(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        merged: ModelT = await self._session.merge(entity)
        await self._session.flush()
        return merged

    async def delete(self, entity_id: IdT) -> None:
        entity = await self.get(entity_id)
        if entity is not None:
            await self._session.delete(entity)
            await self._session.flush()


__all__ = ["SQLAlchemyRepository"]
