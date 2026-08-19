"""src/worktree/core/db package.

Handles offline SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, and unified run execution tracking.
"""

from worktree.core.db.base import DbBase
from worktree.core.db.catalog import CatalogDb
from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)
from worktree.core.db.costs import CostsDb
from worktree.core.db.facade import WorktreeDb
from worktree.core.db.migrations import (
    CREATE_CATALOG_TABLE_SQL,
    CREATE_RUNS_INDEXES_SQL,
    CREATE_RUNS_TABLE_SQL,
    CREATE_SANDBOXES_TABLE_SQL,
    CREATE_WORKFLOW_COSTS_TABLE_SQL,
    init_database,
)
from worktree.core.db.models import (
    BlueprintKind,
    CatalogItemType,
    CatalogRecord,
    RunRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
)
from worktree.core.db.runs import RunsDb
from worktree.core.db.sandboxes import SandboxesDb

__all__ = [
    "CREATE_CATALOG_TABLE_SQL",
    "CREATE_RUNS_INDEXES_SQL",
    "CREATE_RUNS_TABLE_SQL",
    "CREATE_SANDBOXES_TABLE_SQL",
    "CREATE_WORKFLOW_COSTS_TABLE_SQL",
    "DEFAULT_DB_REL_PATH",
    "BlueprintKind",
    "CatalogDb",
    "CatalogItemType",
    "CatalogRecord",
    "CostsDb",
    "DbBase",
    "RunRecord",
    "RunStatus",
    "RunsDb",
    "SandboxRecord",
    "SandboxStatus",
    "SandboxesDb",
    "WorktreeDb",
    "get_db_connection",
    "init_database",
    "resolve_db_path",
]
