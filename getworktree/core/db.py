"""getworktree/core/db.py.

Handles offline SQLite connection pooling, database migrations, financial token
usage tracking, template indexing, workflow run metadata, and task execution runs.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

DEFAULT_DB_REL_PATH = ".worktree/data.db"

# Schema migration DDL for tracking AI model token costs
CREATE_LOOP_COSTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS loop_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_usd_cost REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_loop_costs_session ON loop_costs(session_id);
CREATE INDEX IF NOT EXISTS idx_loop_costs_created ON loop_costs(created_at);
"""

# Schema migration DDL for durable sandbox metadata
CREATE_SANDBOXES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sandboxes (
    id TEXT PRIMARY KEY,
    name TEXT,
    branch_name TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    sandbox_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'merged', 'cleaned', 'conflict')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sandboxes_status ON sandboxes(status);
"""

# Schema migration DDL for template indexing
CREATE_TEMPLATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha TEXT NOT NULL,
    template_type TEXT NOT NULL CHECK(template_type IN ('workflow', 'task', 'step')),
    path TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_templates_sha ON templates(sha);
CREATE INDEX IF NOT EXISTS idx_templates_type ON templates(template_type);
CREATE INDEX IF NOT EXISTS idx_templates_path ON templates(path);
"""

# Schema migration DDL for workflow execution tracking
CREATE_WORKFLOWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    workflow_name TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_workflows_session ON workflows(session_id);
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
"""

# Schema migration DDL for task execution tracking
CREATE_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""


class SandboxStatus(StrEnum):
    """Lifecycle status for a persisted sandbox metadata row."""

    ACTIVE = "active"
    MERGED = "merged"
    CLEANED = "cleaned"
    CONFLICT = "conflict"


class TemplateType(StrEnum):
    """Supported template classification types."""

    WORKFLOW = "workflow"
    TASK = "task"
    STEP = "step"


class RunStatus(StrEnum):
    """Lifecycle status for workflow and task execution sessions."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SandboxRecord(BaseModel):
    """Row shape for the local `sandboxes` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: str
    name: str | None = None
    branch_name: str
    base_commit: str
    sandbox_path: Path
    status: SandboxStatus
    created_at: str
    updated_at: str


class TemplateRecord(BaseModel):
    """Row shape for the local `templates` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    sha: str
    template_type: TemplateType
    path: Path
    checksum: str
    created_at: str
    updated_at: str


class WorkflowRunRecord(BaseModel):
    """Row shape for the local `workflows` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    session_id: str
    workflow_name: str
    branch_name: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    error_message: str | None = None


class TaskRunRecord(BaseModel):
    """Row shape for the local `tasks` table."""

    model_config = {"extra": "forbid", "strict": True}

    id: int
    session_id: str
    task_name: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    error_message: str | None = None


def resolve_db_path(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> Path:
    """Resolve database path relative to project root, ensuring target parent directory exists."""
    base_dir = (cwd or Path.cwd()).resolve()
    db_path = base_dir / db_rel_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def get_db_connection(db_path: Path) -> Generator[sqlite3.Connection]:
    """Context manager offering clean database connection setup and safe teardown."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> Path:
    """Run table migrations and initialize local SQLite database layout."""
    db_path = resolve_db_path(cwd, db_rel_path)
    with get_db_connection(db_path) as conn:
        conn.executescript(CREATE_LOOP_COSTS_TABLE_SQL)
        conn.executescript(CREATE_SANDBOXES_TABLE_SQL)
        conn.executescript(CREATE_TEMPLATES_TABLE_SQL)
        conn.executescript(CREATE_WORKFLOWS_TABLE_SQL)
        conn.executescript(CREATE_TASKS_TABLE_SQL)
    return db_path


def _sandbox_record_from_row(row: sqlite3.Row) -> SandboxRecord:
    """Map a `sandboxes` SQLite row to a strict `SandboxRecord`."""
    return SandboxRecord(
        id=row["id"],
        name=row["name"],
        branch_name=row["branch_name"],
        base_commit=row["base_commit"],
        sandbox_path=Path(row["sandbox_path"]),
        status=SandboxStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _template_record_from_row(row: sqlite3.Row) -> TemplateRecord:
    """Map a `templates` SQLite row to a strict `TemplateRecord`."""
    return TemplateRecord(
        id=row["id"],
        sha=row["sha"],
        template_type=TemplateType(row["template_type"]),
        path=Path(row["path"]),
        checksum=row["checksum"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _workflow_run_record_from_row(row: sqlite3.Row) -> WorkflowRunRecord:
    """Map a `workflows` SQLite row to a strict `WorkflowRunRecord`."""
    return WorkflowRunRecord(
        id=row["id"],
        session_id=row["session_id"],
        workflow_name=row["workflow_name"],
        branch_name=row["branch_name"],
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )


def _task_run_record_from_row(row: sqlite3.Row) -> TaskRunRecord:
    """Map a `tasks` SQLite row to a strict `TaskRunRecord`."""
    return TaskRunRecord(
        id=row["id"],
        session_id=row["session_id"],
        task_name=row["task_name"],
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
    )


def insert_sandbox(
    id: str,
    branch_name: str,
    base_commit: str,
    sandbox_path: Path,
    name: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord:
    """Insert a sandbox metadata row with status ``active``.

    Returns:
        The inserted `SandboxRecord`, including DB-assigned timestamps.

    Raises:
        ValueError: If a row with the same ``id`` already exists.
    """
    db_path = init_database(cwd, db_rel_path)
    insert_sql = """
    INSERT INTO sandboxes (
        id, name, branch_name, base_commit, sandbox_path, status
    ) VALUES (?, ?, ?, ?, ?, ?);
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                insert_sql,
                (
                    id,
                    name,
                    branch_name,
                    base_commit,
                    str(sandbox_path),
                    SandboxStatus.ACTIVE.value,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Sandbox with id '{id}' already exists") from exc
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover - insert just succeeded
            raise RuntimeError(f"Failed to read sandbox row after insert: {id}")
        return _sandbox_record_from_row(row)


def get_sandbox(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> SandboxRecord | None:
    """Return the sandbox row for ``id``, or ``None`` when missing."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def list_sandboxes(
    status: SandboxStatus | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> list[SandboxRecord]:
    """List sandbox rows ordered by ``created_at`` descending.

    When ``status`` is set, only rows with that status are returned.
    """
    db_path = init_database(cwd, db_rel_path)

    if status is None:
        query_sql = "SELECT * FROM sandboxes ORDER BY created_at DESC;"
        params: tuple[object, ...] = ()
    else:
        query_sql = "SELECT * FROM sandboxes WHERE status = ? ORDER BY created_at DESC;"
        params = (status.value,)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        return [_sandbox_record_from_row(row) for row in rows]


def update_sandbox_status(
    id: str,
    status: SandboxStatus,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> SandboxRecord | None:
    """Update sandbox status and ``updated_at``; return the row or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    update_sql = """
    UPDATE sandboxes
    SET status = ?, updated_at = ?
    WHERE id = ?;
    """
    select_sql = "SELECT * FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(update_sql, (status.value, now_utc, id))
        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _sandbox_record_from_row(row) if row is not None else None


def delete_sandbox_row(
    id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> bool:
    """Hard-delete a sandbox metadata row. Returns whether a row was removed."""
    db_path = init_database(cwd, db_rel_path)
    delete_sql = "DELETE FROM sandboxes WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(delete_sql, (id,))
        return cursor.rowcount > 0


def record_token_usage(
    session_id: str,
    branch_name: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_usd_cost: float,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> int | None:
    """Log token consumption and dollar costs for an execution step.

    Returns the auto-incremented primary key ID of the inserted record.
    """
    db_path = init_database(cwd, db_rel_path)
    total_tokens = prompt_tokens + completion_tokens
    now_utc = datetime.now(UTC).isoformat()

    insert_sql = """
    INSERT INTO loop_costs (
        session_id, branch_name, model_id, prompt_tokens,
        completion_tokens, total_tokens, estimated_usd_cost, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                session_id,
                branch_name,
                model_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                estimated_usd_cost,
                now_utc,
            ),
        )
        return cursor.lastrowid


def get_session_total_cost(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> dict[str, float]:
    """Calculate aggregated token counts and dollar spend for a specific execution loop session."""
    db_path = init_database(cwd, db_rel_path)

    query_sql = """
    SELECT
        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
        COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(estimated_usd_cost), 0.0) AS total_usd_cost
    FROM loop_costs
    WHERE session_id = ?;
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, (session_id,))
        row = cursor.fetchone()
        return (
            dict(row)
            if row
            else {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_usd_cost": 0.0,
            }
        )


def upsert_template(
    sha: str,
    template_type: TemplateType | str,
    path: Path,
    checksum: str,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> TemplateRecord:
    """Insert a new template metadata row or update `sha`, `checksum`, and `updated_at` on path match."""
    db_path = init_database(cwd, db_rel_path)
    str_path = str(path)
    type_str = (
        template_type.value
        if isinstance(template_type, TemplateType)
        else str(template_type)
    )
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    upsert_sql = """
    INSERT INTO templates (sha, template_type, path, checksum, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        sha = excluded.sha,
        template_type = excluded.template_type,
        checksum = excluded.checksum,
        updated_at = excluded.updated_at;
    """
    select_sql = "SELECT * FROM templates WHERE path = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                upsert_sql,
                (sha, type_str, str_path, checksum, now_utc, now_utc),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Invalid template insert/update constraint: {exc}"
            ) from exc

        cursor.execute(select_sql, (str_path,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(f"Failed to read template row after upsert: {str_path}")
        return _template_record_from_row(row)


def get_template_by_id(
    id: int, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> TemplateRecord | None:
    """Return the template row matching integer ``id``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM templates WHERE id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (id,))
        row = cursor.fetchone()
        return _template_record_from_row(row) if row is not None else None


def get_template_by_path(
    path: Path, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> TemplateRecord | None:
    """Return the template row matching relative ``path``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM templates WHERE path = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (str(path),))
        row = cursor.fetchone()
        return _template_record_from_row(row) if row is not None else None


def list_templates(
    template_type: TemplateType | str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> list[TemplateRecord]:
    """List template rows, optionally filtered by ``template_type``."""
    db_path = init_database(cwd, db_rel_path)

    if template_type is None:
        query_sql = "SELECT * FROM templates ORDER BY id ASC;"
        params: tuple[object, ...] = ()
    else:
        type_str = (
            template_type.value
            if isinstance(template_type, TemplateType)
            else str(template_type)
        )
        query_sql = "SELECT * FROM templates WHERE template_type = ? ORDER BY id ASC;"
        params = (type_str,)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql, params)
        rows = cursor.fetchall()
        return [_template_record_from_row(row) for row in rows]


def insert_workflow_run(
    session_id: str,
    workflow_name: str,
    branch_name: str,
    status: RunStatus | str = RunStatus.RUNNING,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> WorkflowRunRecord:
    """Insert a workflow run record."""
    db_path = init_database(cwd, db_rel_path)
    status_str = status.value if isinstance(status, RunStatus) else str(status)
    insert_sql = """
    INSERT INTO workflows (session_id, workflow_name, branch_name, status)
    VALUES (?, ?, ?, ?);
    """
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                insert_sql, (session_id, workflow_name, branch_name, status_str)
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Workflow run with session_id '{session_id}' already exists or failed constraints: {exc}"
            ) from exc

        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(
                f"Failed to read workflow run row after insert: {session_id}"
            )
        return _workflow_run_record_from_row(row)


def get_workflow_run(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> WorkflowRunRecord | None:
    """Return the workflow run matching ``session_id``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _workflow_run_record_from_row(row) if row is not None else None


def update_workflow_run_status(
    session_id: str,
    status: RunStatus | str,
    error_message: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> WorkflowRunRecord | None:
    """Update status, optional completed_at timestamp, and error message for a workflow run."""
    db_path = init_database(cwd, db_rel_path)
    status_enum = (
        RunStatus(status)
        if isinstance(status, str) and status in RunStatus._value2member_map_
        else status
    )
    status_str = (
        status_enum.value if isinstance(status_enum, RunStatus) else str(status)
    )

    completed_at = (
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if status_str
        in (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        )
        else None
    )

    update_sql = """
    UPDATE workflows
    SET status = ?, completed_at = ?, error_message = ?
    WHERE session_id = ?;
    """
    select_sql = "SELECT * FROM workflows WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                update_sql, (status_str, completed_at, error_message, session_id)
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Invalid workflow status update constraint: {exc}"
            ) from exc

        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _workflow_run_record_from_row(row) if row is not None else None


def list_workflow_runs(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> list[WorkflowRunRecord]:
    """List workflow run records ordered by ``started_at`` descending."""
    db_path = init_database(cwd, db_rel_path)
    query_sql = "SELECT * FROM workflows ORDER BY started_at DESC;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        rows = cursor.fetchall()
        return [_workflow_run_record_from_row(row) for row in rows]


def insert_task_run(
    session_id: str,
    task_name: str,
    status: RunStatus | str = RunStatus.RUNNING,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> TaskRunRecord:
    """Insert a task run record."""
    db_path = init_database(cwd, db_rel_path)
    status_str = status.value if isinstance(status, RunStatus) else str(status)
    insert_sql = """
    INSERT INTO tasks (session_id, task_name, status)
    VALUES (?, ?, ?);
    """
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(insert_sql, (session_id, task_name, status_str))
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Task run with session_id '{session_id}' already exists or failed constraints: {exc}"
            ) from exc

        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(
                f"Failed to read task run row after insert: {session_id}"
            )
        return _task_run_record_from_row(row)


def get_task_run(
    session_id: str, cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> TaskRunRecord | None:
    """Return the task run matching ``session_id``, or ``None``."""
    db_path = init_database(cwd, db_rel_path)
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _task_run_record_from_row(row) if row is not None else None


def update_task_run_status(
    session_id: str,
    status: RunStatus | str,
    error_message: str | None = None,
    cwd: Path | None = None,
    db_rel_path: str = DEFAULT_DB_REL_PATH,
) -> TaskRunRecord | None:
    """Update status, optional completed_at timestamp, and error message for a task run."""
    db_path = init_database(cwd, db_rel_path)
    status_enum = (
        RunStatus(status)
        if isinstance(status, str) and status in RunStatus._value2member_map_
        else status
    )
    status_str = (
        status_enum.value if isinstance(status_enum, RunStatus) else str(status)
    )

    completed_at = (
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if status_str
        in (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        )
        else None
    )

    update_sql = """
    UPDATE tasks
    SET status = ?, completed_at = ?, error_message = ?
    WHERE session_id = ?;
    """
    select_sql = "SELECT * FROM tasks WHERE session_id = ?;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                update_sql, (status_str, completed_at, error_message, session_id)
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Invalid task status update constraint: {exc}") from exc

        if cursor.rowcount == 0:
            return None
        cursor.execute(select_sql, (session_id,))
        row = cursor.fetchone()
        return _task_run_record_from_row(row) if row is not None else None


def list_task_runs(
    cwd: Path | None = None, db_rel_path: str = DEFAULT_DB_REL_PATH
) -> list[TaskRunRecord]:
    """List task run records ordered by ``started_at`` descending."""
    db_path = init_database(cwd, db_rel_path)
    query_sql = "SELECT * FROM tasks ORDER BY started_at DESC;"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query_sql)
        rows = cursor.fetchall()
        return [_task_run_record_from_row(row) for row in rows]
