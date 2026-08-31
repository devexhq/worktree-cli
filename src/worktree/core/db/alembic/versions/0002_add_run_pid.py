"""Add pid column to runs table.

Revision ID: 0002_add_run_pid
Revises: 0001_initial_schema
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_run_pid"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add pid column to runs table."""
    op.add_column("runs", sa.Column("pid", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop pid column from runs table."""
    op.drop_column("runs", "pid")
