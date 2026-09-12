"""Replace task/workflow catalog and run identity with Blueprint key identity.

Revision ID: 0004_blueprint_catalog_schema
Revises: 0003_add_catalog_namespace
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_blueprint_catalog_schema"
down_revision: str | None = "0003_add_catalog_namespace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add catalog.key and replace runs.kind with blueprint_key; greenfield, no data conversion."""
    with op.batch_alter_table("catalog", schema=None) as batch_op:
        batch_op.add_column(sa.Column("key", sa.String(), nullable=True))
        batch_op.drop_constraint("ck_catalog_item_type", type_="check")
        batch_op.create_check_constraint(
            "ck_catalog_item_type",
            "item_type IN ('blueprint', 'step')",
        )
    op.create_index("idx_catalog_key", "catalog", ["key"], unique=True)

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("blueprint_key", sa.String(), nullable=True))
        batch_op.drop_constraint("ck_runs_kind", type_="check")
        batch_op.drop_column("kind")


def downgrade() -> None:
    """Restore runs.kind and drop catalog.key."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(), nullable=False, server_default="task"))
        batch_op.create_check_constraint(
            "ck_runs_kind",
            "kind IN ('task', 'workflow')",
        )
        batch_op.drop_column("blueprint_key")

    op.drop_index("idx_catalog_key", table_name="catalog")
    with op.batch_alter_table("catalog", schema=None) as batch_op:
        batch_op.drop_constraint("ck_catalog_item_type", type_="check")
        batch_op.create_check_constraint(
            "ck_catalog_item_type",
            "item_type IN ('workflow', 'task', 'step')",
        )
        batch_op.drop_column("key")
