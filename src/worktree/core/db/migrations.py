"""Database migration routines using Alembic programmatic API."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from worktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    resolve_db_path,
    sqlite_url,
)

INITIAL_SCHEMA_REVISION = "0001_initial_schema"


def init_database(
    path: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
    db_path: Path | None = None,
) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    if db_path is not None:
        target_path = db_path
    elif path is not None:
        target_path = resolve_db_path(path, db_rel_path)
    else:
        raise ValueError("Either path or db_path must be provided to init_database.")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    alembic_cfg = Config()
    alembic_dir = Path(__file__).parent / "alembic"
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url(target_path))

    command.upgrade(alembic_cfg, "head")

    return target_path
