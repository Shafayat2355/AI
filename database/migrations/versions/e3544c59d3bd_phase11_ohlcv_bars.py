"""Phase 11: ohlcv_bars table

Backs ``database.repositories.ohlcv_bar_repository.OHLCVBarModel`` -- the
persisted source data ``feature_engineering/offline_pipeline.py`` reads to
compute technical/statistical features, and that Feast's offline store
(materialized to parquet by that same pipeline) is ultimately derived from.

Revision ID: e3544c59d3bd
Revises: 130f3304b3d4
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3544c59d3bd"
down_revision: str | None = "130f3304b3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ohlcv_bars",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.DECIMAL(precision=24, scale=8), nullable=False),
        sa.Column("high", sa.DECIMAL(precision=24, scale=8), nullable=False),
        sa.Column("low", sa.DECIMAL(precision=24, scale=8), nullable=False),
        sa.Column("close", sa.DECIMAL(precision=24, scale=8), nullable=False),
        sa.Column("volume", sa.DECIMAL(precision=28, scale=8), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ohlcv_bars")),
        sa.UniqueConstraint(
            "symbol", "interval", "open_time", name="uq_ohlcv_bars_symbol_interval_open_time"
        ),
    )
    op.create_index(
        "ix_ohlcv_bars_symbol_interval_open_time",
        "ohlcv_bars",
        ["symbol", "interval", "open_time"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ohlcv_bars_symbol_interval_open_time", table_name="ohlcv_bars")
    op.drop_table("ohlcv_bars")
