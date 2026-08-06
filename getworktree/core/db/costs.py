"""CRUD helpers for tracking token consumption and workflow costs in SQLite."""

from datetime import UTC, datetime
from pathlib import Path

from getworktree.core.db.connection import (
    DEFAULT_DB_REL_PATH,
    get_db_connection,
)
from getworktree.core.db.migrations import init_database


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
    INSERT INTO workflow_costs (
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
    """Calculate aggregated token counts and dollar spend for a specific execution workflow session."""
    db_path = init_database(cwd, db_rel_path)

    query_sql = """
    SELECT
        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
        COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(estimated_usd_cost), 0.0) AS total_usd_cost
    FROM workflow_costs
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
