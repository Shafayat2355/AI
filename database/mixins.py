"""Reusable declarative mixins for ORM models mapped against :class:`database.base.Base`.

Phase 6 established ``Base`` itself (the single ``DeclarativeBase``) and
``session_scope`` (a transactional helper). This module adds the common *columns*
almost every mapped table wants -- a UUID primary key, created/updated timestamps,
a soft-delete marker, and audit (who changed this row) fields -- as independent
mixins a concrete model composes with ``Base``, rather than each future domain
model (``core/domain``'s eventual ``Order``, ``Position``, ...) redeclaring the
same columns.

Usage::

    from database.base import Base
    from database.mixins import AuditedBase  # Base + every mixin below, the
                                              # common case for a mutable,
                                              # soft-deletable, audited table

    class Order(AuditedBase):
        __tablename__ = "orders"
        symbol: Mapped[str]
        ...

A table that genuinely does not want one of these behaviors (an append-only
audit-log table itself should not be soft-deletable, for instance) composes
``Base`` with only the mixins it needs instead of using :class:`AuditedBase`::

    class AuditLogEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
        __tablename__ = "audit_log_entries"
        ...
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


def _utcnow() -> datetime:
    """Timezone-aware "now", used as every timestamp column's Python-side default.

    A callable default (rather than ``datetime.utcnow`` passed by reference, which
    is naive) so every row gets a real, timezone-aware ``UTC`` timestamp regardless
    of backend -- SQLite has no native ``TIMESTAMPTZ`` and would otherwise silently
    drop the timezone.
    """
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    """Adds a UUIDv4 primary key column named ``id``.

    Generated client-side (Python's ``uuid.uuid4``, via the column default) rather
    than server-side (Postgres ``gen_random_uuid()``): the id is assigned when the
    object is flushed to the session (SQLAlchemy applies ``default=`` during
    flush, not at ``__init__`` time), without a round trip to the database to
    read back a server-generated value -- one fewer query per insert compared to
    a server-side default, and the same id-generation behavior on every backend
    (SQLite has no ``gen_random_uuid()`` equivalent, which matters for the
    SQLite-backed test suite).
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Adds automatically-maintained ``created_at``/``updated_at`` columns.

    Both are set by the Python-side default/``onupdate`` hook (:func:`_utcnow`),
    which runs identically against Postgres and the SQLite backend used by tests
    -- a ``server_default=func.now()`` approach would work for Postgres but not
    reproduce ``onupdate`` behavior identically across both dialects.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SoftDeleteMixin:
    """Adds a ``deleted_at`` column marking a row as (soft-)deleted.

    ``NULL`` means "not deleted" -- the common, indexable convention. Pairs with
    ``database.repositories.soft_delete_repository.SoftDeleteRepository``, which
    sets this column instead of removing the row and filters it out of
    ``get``/``list`` by default.

    A concrete model combining this with other mixins should declare its own
    ``__table_args__`` (e.g. a partial index on ``deleted_at IS NULL``) rather
    than relying on any mixin to contribute one automatically -- with multiple
    mixins in one MRO, only one class's ``__table_args__`` would ever take
    effect, silently dropping the others. See
    ``docs/PHASE7_DATABASE_LAYER.md`` "Index strategy" for the recommended
    index per column this module adds.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )

    @property
    def is_deleted(self) -> bool:
        """Whether this row has been soft-deleted."""
        return self.deleted_at is not None


class AuditMixin:
    """Adds ``created_by``/``updated_by`` columns recording *who* changed a row.

    Deliberately a plain, nullable string identifier (a user id, service name, or
    ``"system"``) rather than a foreign key to an eventual ``users`` table, which
    does not exist yet -- this mirrors
    ``shared.logging.audit.log_audit_event``'s ``actor`` field so the same value
    can be threaded through both the audit *log* and the audit *columns*. A
    concrete model in a later phase may tighten this to a real foreign key once a
    users table exists, without changing this mixin's column names.
    """

    created_by: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), default=None, nullable=True)


class AuditedBase(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """Convenience combination of every mixin above -- the common case.

    ``__abstract__ = True`` so this class itself is never mapped to a table; only
    its concrete subclasses are.
    """

    __abstract__ = True


__all__ = [
    "AuditMixin",
    "AuditedBase",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
