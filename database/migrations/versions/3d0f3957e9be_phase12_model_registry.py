"""Phase 12: model registry tables (training_runs, model_versions, model_evaluations)

Backs ``models.registry_client.PostgresModelRegistry`` --
``core.ports.model_registry_port.ModelRegistryPort``'s concrete
implementation. ``model_versions.training_run_id`` and
``model_evaluations.model_version_id`` are real foreign keys;
``training_runs.model_version_id`` is a plain (unconstrained) UUID column --
see ``models/registry_client.py``'s ``TrainingRunModel`` docstring for why.

Revision ID: 3d0f3957e9be
Revises: e3544c59d3bd
Create Date: 2026-08-25 00:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d0f3957e9be"
down_revision: str | None = "e3544c59d3bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "training_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("feature_refs", sa.JSON(), nullable=False),
        sa.Column("dataset_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_split", sa.Float(), nullable=False),
        sa.Column("validation_split", sa.Float(), nullable=False),
        sa.Column("test_split", sa.Float(), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), nullable=False),
        sa.Column("library_versions", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_runs")),
    )
    op.create_index("ix_training_runs_model_name", "training_runs", ["model_name"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=False),
        sa.Column("training_run_id", sa.Uuid(), nullable=False),
        sa.Column("feature_refs", sa.JSON(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("was_production", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["training_run_id"],
            ["training_runs.id"],
            name=op.f("fk_model_versions_training_run_id_training_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_versions")),
        sa.UniqueConstraint("model_name", "version", name="uq_model_versions_name_version"),
    )
    op.create_index("ix_model_versions_model_name_stage", "model_versions", ["model_name", "stage"])

    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("split", sa.String(length=16), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=False),
        sa.Column("recall", sa.Float(), nullable=False),
        sa.Column("f1_score", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("extra_metrics", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_model_evaluations_model_version_id_model_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_evaluations")),
    )
    op.create_index(
        "ix_model_evaluations_model_version_id", "model_evaluations", ["model_version_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_model_evaluations_model_version_id", table_name="model_evaluations")
    op.drop_table("model_evaluations")
    op.drop_index("ix_model_versions_model_name_stage", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index("ix_training_runs_model_name", table_name="training_runs")
    op.drop_table("training_runs")
