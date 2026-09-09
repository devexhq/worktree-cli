"""Add namespace column to catalog.

Revision ID: 0003_add_catalog_namespace
Revises: 0002_add_run_pid
Create Date: 2026-09-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_catalog_namespace"
down_revision: str | None = "0002_add_run_pid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional namespace metadata to catalog rows."""
    op.add_column("catalog", sa.Column("namespace", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove optional namespace metadata from catalog rows."""
    op.drop_column("catalog", "namespace")
