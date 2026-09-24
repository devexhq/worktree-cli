"""Initial baseline database schema migration.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel import AutoString

from worktree.core.db.migrations import INITIAL_SCHEMA_REVISION

# revision identifiers, used by Alembic.
revision: str = INITIAL_SCHEMA_REVISION
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create centralized, project-scoped tables for sandboxes, catalog, runs, and costs."""
    op.create_table(
        "sandboxes",
        sa.Column("id", AutoString(), nullable=False),
        sa.Column("project_id", AutoString(), nullable=False),
        sa.Column("name", AutoString(), nullable=True),
        sa.Column("branch_name", AutoString(), nullable=False),
        sa.Column("base_commit", AutoString(), nullable=False),
        sa.Column("sandbox_path", AutoString(), nullable=False),
        sa.Column("status", AutoString(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sandbox_path"),
        sa.CheckConstraint(
            "status IN ('active', 'merged', 'cleaned', 'conflict')",
            name="ck_sandboxes_status",
        ),
    )
    op.create_index("idx_sandboxes_status", "sandboxes", ["status"], unique=False)
    op.create_index("idx_sandboxes_project_id", "sandboxes", ["project_id"], unique=False)

    op.create_table(
        "catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", AutoString(), nullable=False),
        sa.Column("key", AutoString(), nullable=False),
        sa.Column("sha", AutoString(), nullable=False),
        sa.Column("item_type", AutoString(), nullable=False),
        sa.Column("name", AutoString(), nullable=False),
        sa.Column("namespace", AutoString(), nullable=True),
        sa.Column("path", AutoString(), nullable=False),
        sa.Column("checksum", AutoString(), nullable=False),
        sa.Column(
            "created_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_catalog_project_key"),
        sa.UniqueConstraint("project_id", "sha", name="uq_catalog_project_sha"),
        sa.UniqueConstraint("project_id", "path", name="uq_catalog_project_path"),
        sa.CheckConstraint(
            "item_type IN ('blueprint', 'step')",
            name="ck_catalog_item_type",
        ),
    )
    op.create_index("idx_catalog_type", "catalog", ["item_type"], unique=False)

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", AutoString(), nullable=False),
        sa.Column("session_id", AutoString(), nullable=False),
        sa.Column("blueprint_key", AutoString(), nullable=False),
        sa.Column("blueprint_name", AutoString(), nullable=False),
        sa.Column("branch_name", AutoString(), nullable=False, server_default=""),
        sa.Column("status", AutoString(), nullable=False, server_default="running"),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", AutoString(), nullable=True),
        sa.Column("error_message", AutoString(), nullable=True),
        sa.Column("checkpoint_json", AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled', 'paused')",
            name="ck_runs_status",
        ),
    )
    op.create_index("idx_runs_status", "runs", ["status"], unique=False)
    op.create_index("idx_runs_started", "runs", ["started_at"], unique=False)
    op.create_index("idx_runs_project_id", "runs", ["project_id"], unique=False)

    op.create_table(
        "costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", AutoString(), nullable=False),
        sa.Column("session_id", AutoString(), nullable=False),
        sa.Column("branch_name", AutoString(), nullable=False),
        sa.Column("model_id", AutoString(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_usd_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            AutoString(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_costs_session", "costs", ["session_id"], unique=False)
    op.create_index("idx_costs_created", "costs", ["created_at"], unique=False)
    op.create_index("idx_costs_project_id", "costs", ["project_id"], unique=False)


def downgrade() -> None:
    """Drop all tables created in initial migration."""
    op.drop_index("idx_costs_project_id", table_name="costs")
    op.drop_index("idx_costs_created", table_name="costs")
    op.drop_index("idx_costs_session", table_name="costs")
    op.drop_table("costs")

    op.drop_index("idx_runs_project_id", table_name="runs")
    op.drop_index("idx_runs_started", table_name="runs")
    op.drop_index("idx_runs_status", table_name="runs")
    op.drop_table("runs")

    op.drop_index("idx_catalog_type", table_name="catalog")
    op.drop_table("catalog")

    op.drop_index("idx_sandboxes_project_id", table_name="sandboxes")
    op.drop_index("idx_sandboxes_status", table_name="sandboxes")
    op.drop_table("sandboxes")
