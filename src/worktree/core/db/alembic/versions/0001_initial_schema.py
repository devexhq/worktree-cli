"""Initial baseline database schema migration.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel import AutoString

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial tables for sandboxes, catalog, runs, and workflow_costs."""
    op.create_table(
        "sandboxes",
        sa.Column("id", AutoString(), nullable=False),
        sa.Column("name", AutoString(), nullable=True),
        sa.Column("branch_name", AutoString(), nullable=False),
        sa.Column("base_commit", AutoString(), nullable=False),
        sa.Column("sandbox_path", AutoString(), nullable=False),
        sa.Column("status", AutoString(), nullable=False, server_default="active"),
        sa.Column("created_at", AutoString(), nullable=False),
        sa.Column("updated_at", AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sandbox_path"),
    )
    op.create_index("idx_sandboxes_status", "sandboxes", ["status"], unique=False)

    op.create_table(
        "catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sha", AutoString(), nullable=False),
        sa.Column("item_type", AutoString(), nullable=False),
        sa.Column("name", AutoString(), nullable=False),
        sa.Column("path", AutoString(), nullable=False),
        sa.Column("checksum", AutoString(), nullable=False),
        sa.Column("created_at", AutoString(), nullable=False),
        sa.Column("updated_at", AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
        sa.UniqueConstraint("sha"),
    )
    op.create_index("idx_catalog_sha", "catalog", ["sha"], unique=True)
    op.create_index("idx_catalog_type", "catalog", ["item_type"], unique=False)
    op.create_index("idx_catalog_path", "catalog", ["path"], unique=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", AutoString(), nullable=False),
        sa.Column("blueprint_name", AutoString(), nullable=False),
        sa.Column("kind", AutoString(), nullable=False),
        sa.Column("branch_name", AutoString(), nullable=False, server_default=""),
        sa.Column("status", AutoString(), nullable=False, server_default="running"),
        sa.Column("started_at", AutoString(), nullable=False),
        sa.Column("completed_at", AutoString(), nullable=True),
        sa.Column("error_message", AutoString(), nullable=True),
        sa.Column("checkpoint_json", AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("idx_runs_session", "runs", ["session_id"], unique=True)
    op.create_index("idx_runs_status", "runs", ["status"], unique=False)
    op.create_index("idx_runs_started", "runs", ["started_at"], unique=False)

    op.create_table(
        "workflow_costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", AutoString(), nullable=False),
        sa.Column("branch_name", AutoString(), nullable=False),
        sa.Column("model_id", AutoString(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_usd_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workflow_costs_session", "workflow_costs", ["session_id"], unique=False)
    op.create_index("idx_workflow_costs_created", "workflow_costs", ["created_at"], unique=False)


def downgrade() -> None:
    """Drop all tables created in initial migration."""
    op.drop_index("idx_workflow_costs_created", table_name="workflow_costs")
    op.drop_index("idx_workflow_costs_session", table_name="workflow_costs")
    op.drop_table("workflow_costs")

    op.drop_index("idx_runs_started", table_name="runs")
    op.drop_index("idx_runs_status", table_name="runs")
    op.drop_index("idx_runs_session", table_name="runs")
    op.drop_table("runs")

    op.drop_index("idx_catalog_path", table_name="catalog")
    op.drop_index("idx_catalog_type", table_name="catalog")
    op.drop_index("idx_catalog_sha", table_name="catalog")
    op.drop_table("catalog")

    op.drop_index("idx_sandboxes_status", table_name="sandboxes")
    op.drop_table("sandboxes")
