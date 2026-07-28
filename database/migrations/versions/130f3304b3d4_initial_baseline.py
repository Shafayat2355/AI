"""initial baseline

Revision ID: 130f3304b3d4
Revises:
Create Date: 2026-07-27 00:00:00.000000

Intentionally empty. No concrete mapped ORM model exists yet in this codebase as
of Phase 7 -- ``database.mixins`` provides reusable columns (UUID primary key,
timestamps, audit fields, soft delete) for a future model to compose with
``database.base.Base``, but nothing has done so yet (see
``docs/PHASE7_DATABASE_LAYER.md`` "Initial migration"). This revision exists so
Alembic's version table (``alembic_version``) is established and every later
migration has one common ancestor to chain from, rather than each service's
first real migration having ``down_revision = None``.
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "130f3304b3d4"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
