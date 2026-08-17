"""src/worktree/core/db package.

Handles offline SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, workflow run metadata, and task execution runs.
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
    CREATE_SANDBOXES_TABLE_SQL,
    CREATE_TASKS_TABLE_SQL,
    CREATE_WORKFLOW_COSTS_TABLE_SQL,
    CREATE_WORKFLOWS_TABLE_SQL,
    init_database,
)
from worktree.core.db.models import (
    CatalogItemType,
    CatalogRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
    TaskRunRecord,
    WorkflowRunRecord,
)
from worktree.core.db.run_tracking import RunTrackingDb
from worktree.core.db.sandboxes import SandboxesDb
from worktree.core.db.tasks import TasksDb
from worktree.core.db.workflows import WorkflowsDb

__all__ = [
    "CREATE_CATALOG_TABLE_SQL",
    "CREATE_SANDBOXES_TABLE_SQL",
    "CREATE_TASKS_TABLE_SQL",
    "CREATE_WORKFLOWS_TABLE_SQL",
    "CREATE_WORKFLOW_COSTS_TABLE_SQL",
    "DEFAULT_DB_REL_PATH",
    "CatalogDb",
    "CatalogItemType",
    "CatalogRecord",
    "CostsDb",
    "DbBase",
    "RunStatus",
    "RunTrackingDb",
    "SandboxRecord",
    "SandboxStatus",
    "SandboxesDb",
    "TaskRunRecord",
    "TasksDb",
    "WorkflowRunRecord",
    "WorkflowsDb",
    "WorktreeDb",
    "get_db_connection",
    "init_database",
    "resolve_db_path",
]
