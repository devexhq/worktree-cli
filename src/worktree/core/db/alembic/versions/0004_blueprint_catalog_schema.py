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
    """Add catalog.key and replace runs.kind with blueprint_key; migrating legacy data."""
    insp = sa.inspect(op.get_bind())
    existing_catalog_checks = {c["name"] for c in insp.get_check_constraints("catalog") if c.get("name")}

    with op.batch_alter_table("catalog", schema=None) as batch_op:
        batch_op.add_column(sa.Column("key", sa.String(), nullable=True))
        if "ck_catalog_item_type" in existing_catalog_checks:
            batch_op.drop_constraint("ck_catalog_item_type", type_="check")

    op.execute(sa.text("UPDATE catalog SET item_type = 'blueprint' WHERE item_type IN ('workflow', 'task')"))
    op.execute(
        sa.text(
            """
            UPDATE catalog
            SET key = CASE
                WHEN namespace IS NOT NULL AND namespace != '' THEN namespace || '/' || name
                ELSE name
            END
            WHERE key IS NULL
            """
        )
    )

    with op.batch_alter_table("catalog", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_catalog_item_type",
            "item_type IN ('blueprint', 'step')",
        )
    op.create_index("idx_catalog_key", "catalog", ["key"], unique=True)

    existing_runs_checks = {c["name"] for c in insp.get_check_constraints("runs") if c.get("name")}
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("blueprint_key", sa.String(), nullable=True))
        if "ck_runs_kind" in existing_runs_checks:
            batch_op.drop_constraint("ck_runs_kind", type_="check")
        batch_op.drop_column("kind")

    op.execute(sa.text("UPDATE runs SET blueprint_key = blueprint_name WHERE blueprint_key IS NULL"))


def downgrade() -> None:
    """Restore runs.kind and drop catalog.key."""
    insp = sa.inspect(op.get_bind())
    existing_runs_checks = {c["name"] for c in insp.get_check_constraints("runs") if c.get("name")}
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(), nullable=False, server_default="task"))
        if "ck_runs_kind" in existing_runs_checks:
            batch_op.drop_constraint("ck_runs_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_runs_kind",
            "kind IN ('task', 'workflow')",
        )
        batch_op.drop_column("blueprint_key")

    op.drop_index("idx_catalog_key", table_name="catalog")
    existing_catalog_checks = {c["name"] for c in insp.get_check_constraints("catalog") if c.get("name")}
    with op.batch_alter_table("catalog", schema=None) as batch_op:
        if "ck_catalog_item_type" in existing_catalog_checks:
            batch_op.drop_constraint("ck_catalog_item_type", type_="check")
        batch_op.drop_column("key")

    op.execute(sa.text("UPDATE catalog SET item_type = 'workflow' WHERE item_type = 'blueprint'"))

    with op.batch_alter_table("catalog", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_catalog_item_type",
            "item_type IN ('workflow', 'task', 'step')",
        )
