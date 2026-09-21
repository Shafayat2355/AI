"""Add atomic per-model version counters.

Revision ID: 7b28c56f5aa1
Revises: 3d0f3957e9be
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b28c56f5aa1"
down_revision: str | None = "3d0f3957e9be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_version_counters",
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("next_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("model_name", name=op.f("pk_model_version_counters")),
    )
    # Preserve the next version for installations that already have model
    # versions from the preceding Phase 12 migration.
    op.execute(
        "INSERT INTO model_version_counters (model_name, next_version) "
        "SELECT model_name, MAX(version) + 1 FROM model_versions "
        "GROUP BY model_name"
    )


def downgrade() -> None:
    op.drop_table("model_version_counters")
