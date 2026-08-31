"""Database migration routines using Alembic programmatic API."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from worktree.common.lock import WorkspaceLock
from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    resolve_db_path,
    sqlite_url,
)

INITIAL_SCHEMA_REVISION = "0001_initial_schema"
LATEST_SCHEMA_REVISION = "0002_add_run_pid"


def init_database(
    path: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
    db_path: Path | None = None,
) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    if db_path is not None:
        target_path = db_path
        root_dir = target_path.parent.parent if target_path.parent.name == ".worktree" else target_path.parent
    elif path is not None:
        target_path = resolve_db_path(path, db_rel_path)
        root_dir = path
    else:
        raise ValueError("Either path or db_path must be provided to init_database.")

    with WorkspaceLock(root_dir):
        target_path.parent.mkdir(parents=True, exist_ok=True)

        alembic_cfg = Config()
        alembic_dir = Path(__file__).parent / "alembic"
        alembic_cfg.set_main_option("script_location", str(alembic_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url(target_path))

        command.upgrade(alembic_cfg, "head")

        return target_path
