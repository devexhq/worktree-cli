"""getworktree/core/db package.

Handles offline SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, workflow run metadata, and task execution runs.
"""

from getworktree.core.db.base import DbBase
from getworktree.core.db.catalog import CatalogDb
from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)
from getworktree.core.db.costs import CostsDb
from getworktree.core.db.facade import WorktreeDb
from getworktree.core.db.migrations import (
    CREATE_CATALOG_TABLE_SQL,
    CREATE_SANDBOXES_TABLE_SQL,
    CREATE_TASKS_TABLE_SQL,
    CREATE_WORKFLOW_COSTS_TABLE_SQL,
    CREATE_WORKFLOWS_TABLE_SQL,
    init_database,
)
from getworktree.core.db.models import (
    CatalogItemType,
    CatalogRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
    TaskRunRecord,
    WorkflowRunRecord,
)
from getworktree.core.db.sandboxes import SandboxesDb
from getworktree.core.db.tasks import TasksDb
from getworktree.core.db.workflows import WorkflowsDb

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
