"""getworktree/core/db package.

Handles offline SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, workflow run metadata, and task execution runs.
"""

from getworktree.core.db.catalog import (
    delete_catalog_item,
    get_catalog_item_by_name,
    get_catalog_item_by_sha,
    list_catalog_items,
    upsert_catalog_item,
)
from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    resolve_db_path,
)
from getworktree.core.db.costs import (
    get_session_total_cost,
    record_token_usage,
)
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
from getworktree.core.db.sandboxes import (
    delete_sandbox_row,
    get_sandbox,
    insert_sandbox,
    list_sandboxes,
    update_sandbox_status,
)
from getworktree.core.db.tasks import (
    get_task_run,
    insert_task_run,
    list_task_runs,
    update_task_run_status,
)
from getworktree.core.db.workflows import (
    get_workflow_run,
    insert_workflow_run,
    list_workflow_runs,
    update_workflow_run_status,
)

__all__ = [
    "CREATE_CATALOG_TABLE_SQL",
    "CREATE_SANDBOXES_TABLE_SQL",
    "CREATE_TASKS_TABLE_SQL",
    "CREATE_WORKFLOWS_TABLE_SQL",
    "CREATE_WORKFLOW_COSTS_TABLE_SQL",
    "DEFAULT_DB_REL_PATH",
    "CatalogItemType",
    "CatalogRecord",
    "RunStatus",
    "SandboxRecord",
    "SandboxStatus",
    "TaskRunRecord",
    "WorkflowRunRecord",
    "delete_catalog_item",
    "delete_sandbox_row",
    "get_catalog_item_by_name",
    "get_catalog_item_by_sha",
    "get_db_connection",
    "get_sandbox",
    "get_session_total_cost",
    "get_task_run",
    "get_workflow_run",
    "init_database",
    "insert_sandbox",
    "insert_task_run",
    "insert_workflow_run",
    "list_catalog_items",
    "list_sandboxes",
    "list_task_runs",
    "list_workflow_runs",
    "record_token_usage",
    "resolve_db_path",
    "update_sandbox_status",
    "update_task_run_status",
    "update_workflow_run_status",
    "upsert_catalog_item",
]
