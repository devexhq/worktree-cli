"""src/worktree/core/db package.

Handles SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, and unified run execution tracking.
"""

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    get_engine,
    get_session,
    resolve_db_path,
    sqlite_url,
)
from worktree.core.db.facade import WorktreeDb
from worktree.core.db.migrations import (
    INITIAL_SCHEMA_REVISION,
    LATEST_SCHEMA_REVISION,
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
    WorkflowCostRecord,
    parse_timestamp,
)
from worktree.core.db.repositories import (
    BaseRepository,
    CatalogRepository,
    CostsRepository,
    RunsRepository,
    SandboxesRepository,
)

__all__ = [
    "DEFAULT_DB_REL_PATH",
    "INITIAL_SCHEMA_REVISION",
    "LATEST_SCHEMA_REVISION",
    "BaseRepository",
    "BlueprintKind",
    "CatalogItemType",
    "CatalogRecord",
    "CatalogRepository",
    "CostsRepository",
    "RunRecord",
    "RunStatus",
    "RunsRepository",
    "SandboxRecord",
    "SandboxStatus",
    "SandboxesRepository",
    "WorkflowCostRecord",
    "WorktreeDb",
    "get_db_connection",
    "get_engine",
    "get_session",
    "init_database",
    "parse_timestamp",
    "resolve_db_path",
    "sqlite_url",
]
