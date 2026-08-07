"""CRUD helpers for tracking token consumption and workflow costs in SQLite using CostsDb repository."""

from datetime import UTC, datetime

from getworktree.core.db.base import DbBase


class CostsDb(DbBase):
    """Repository managing workflow token usage and cost tracking in SQLite."""

    def record_token_usage(
        self,
        session_id: str,
        branch_name: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated_usd_cost: float,
    ) -> int | None:
        """Log token consumption and dollar costs for an execution step.

        Returns the auto-incremented primary key ID of the inserted record.
        """
        total_tokens = prompt_tokens + completion_tokens
        now_utc = datetime.now(UTC).isoformat()

        insert_sql = """
        INSERT INTO workflow_costs (
            session_id, branch_name, model_id, prompt_tokens,
            completion_tokens, total_tokens, estimated_usd_cost, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        return self.execute_insert(
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

    def get_session_total_cost(self, session_id: str) -> dict[str, float]:
        """Calculate aggregated token counts and dollar spend for a specific execution workflow session."""
        query_sql = """
        SELECT
            COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_usd_cost), 0.0) AS total_usd_cost
        FROM workflow_costs
        WHERE session_id = ?;
        """
        row = self.fetch_one(query_sql, (session_id,))
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
