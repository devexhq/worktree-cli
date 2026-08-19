"""src/worktree/core/db package.

Handles SQLite connection management, database migrations, financial token
usage tracking, catalog indexing, and unified run execution tracking.
"""

from worktree.core.db.base import DbBase
from worktree.core.db.catalog import CatalogDb
from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
    get_engine,
    get_session,
    resolve_db_path,
)
from worktree.core.db.costs import CostsDb
from worktree.core.db.facade import WorktreeDb
from worktree.core.db.migrations import init_database
from worktree.core.db.models import (
    BlueprintKind,
    CatalogItemType,
    CatalogRecord,
    RunRecord,
    RunStatus,
    SandboxRecord,
    SandboxStatus,
    WorkflowCostRecord,
)
from worktree.core.db.repositories import BaseRepository
from worktree.core.db.runs import RunsDb
from worktree.core.db.sandboxes import SandboxesDb

__all__ = [
    "DEFAULT_DB_REL_PATH",
    "BaseRepository",
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
    "WorkflowCostRecord",
    "WorktreeDb",
    "get_db_connection",
    "get_engine",
    "get_session",
    "init_database",
    "resolve_db_path",
]
