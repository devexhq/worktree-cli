"""Drop the retired catalog table.

Revision ID: 0002_drop_catalog_table
Revises: 0001_initial_schema
Create Date: 2026-09-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel import AutoString

# revision identifiers, used by Alembic.
revision: str = "0002_drop_catalog_table"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the retired catalog table and its item_type index."""
    op.drop_index("idx_catalog_type", table_name="catalog")
    op.drop_table("catalog")


def downgrade() -> None:
    """Recreate the catalog table and its item_type index exactly as 0001_initial_schema defined them."""
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
