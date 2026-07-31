"""Tests for SQLite token usage helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from getworktree.core.db import (
    get_session_total_cost,
    init_database,
    record_token_usage,
)


class DatabaseTests:
    """Tests for init/record/aggregate token usage."""

    def test_init_creates_db(self, tmp_path: Path) -> None:
        db_path = init_database(cwd=tmp_path, db_rel_path=".worktree/token_audit.db")
        assert db_path.is_file()

    def test_record_and_aggregate(self, tmp_path: Path) -> None:
        row_id = record_token_usage(
            session_id="s1",
            branch_name="feature",
            model_id="m",
            prompt_tokens=10,
            completion_tokens=5,
            estimated_usd_cost=0.01,
            cwd=tmp_path,
            db_rel_path=".worktree/token_audit.db",
        )
        assert row_id is not None

        totals = get_session_total_cost(
            "s1", cwd=tmp_path, db_rel_path=".worktree/token_audit.db"
        )
        assert totals["total_prompt_tokens"] == 10
        assert totals["total_completion_tokens"] == 5
        assert totals["total_tokens"] == 15
        assert totals["total_usd_cost"] == pytest.approx(0.01)

    def test_empty_session_totals(self, tmp_path: Path) -> None:
        init_database(cwd=tmp_path, db_rel_path=".worktree/token_audit.db")
        totals = get_session_total_cost(
            "missing", cwd=tmp_path, db_rel_path=".worktree/token_audit.db"
        )
        assert totals["total_tokens"] == 0
        assert totals["total_usd_cost"] == 0.0
