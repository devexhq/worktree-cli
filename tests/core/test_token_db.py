"""Tests for SQLite token usage and sandbox metadata helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from getworktree.core.db import (
    SandboxStatus,
    delete_sandbox_row,
    get_sandbox,
    get_session_total_cost,
    init_database,
    insert_sandbox,
    list_sandboxes,
    record_token_usage,
    update_sandbox_status,
)

DB_REL = ".worktree/data.db"


class DatabaseTests:
    """Tests for init/record/aggregate token usage."""

    def test_init_creates_db(self, tmp_path: Path) -> None:
        db_path = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        assert db_path.is_file()

        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert "loop_costs" in tables
        assert "sandboxes" in tables

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        first = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        second = init_database(cwd=tmp_path, db_rel_path=DB_REL)
        assert first == second
        assert first.is_file()

    def test_record_and_aggregate(self, tmp_path: Path) -> None:
        row_id = record_token_usage(
            session_id="s1",
            branch_name="feature",
            model_id="m",
            prompt_tokens=10,
            completion_tokens=5,
            estimated_usd_cost=0.01,
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        assert row_id is not None

        totals = get_session_total_cost("s1", cwd=tmp_path, db_rel_path=DB_REL)
        assert totals["total_prompt_tokens"] == 10
        assert totals["total_completion_tokens"] == 5
        assert totals["total_tokens"] == 15
        assert totals["total_usd_cost"] == pytest.approx(0.01)

    def test_empty_session_totals(self, tmp_path: Path) -> None:
        init_database(cwd=tmp_path, db_rel_path=DB_REL)
        totals = get_session_total_cost("missing", cwd=tmp_path, db_rel_path=DB_REL)
        assert totals["total_tokens"] == 0
        assert totals["total_usd_cost"] == 0.0


class SandboxDatabaseTests:
    """Tests for sandboxes table CRUD helpers."""

    def _insert(
        self,
        tmp_path: Path,
        *,
        sandbox_id: str = "sbx_a1b2c3d4",
        name: str | None = "alpha",
        path_suffix: str = "a",
    ):
        return insert_sandbox(
            id=sandbox_id,
            branch_name=f"worktree/sandbox-{sandbox_id}",
            base_commit="abc123",
            sandbox_path=tmp_path / ".worktree" / "sandboxes" / path_suffix,
            name=name,
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

    def test_insert_and_get_sandbox(self, tmp_path: Path) -> None:
        created = self._insert(tmp_path)
        assert created.id == "sbx_a1b2c3d4"
        assert created.name == "alpha"
        assert created.branch_name == "worktree/sandbox-sbx_a1b2c3d4"
        assert created.base_commit == "abc123"
        assert created.sandbox_path == (tmp_path / ".worktree" / "sandboxes" / "a")
        assert created.status is SandboxStatus.ACTIVE
        assert created.created_at
        assert created.updated_at

        loaded = get_sandbox("sbx_a1b2c3d4", cwd=tmp_path, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded == created

    def test_insert_name_none_stores_null(self, tmp_path: Path) -> None:
        created = self._insert(tmp_path, name=None)
        assert created.name is None
        loaded = get_sandbox(created.id, cwd=tmp_path, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.name is None

    def test_insert_duplicate_id_raises(self, tmp_path: Path) -> None:
        self._insert(tmp_path, sandbox_id="dup", path_suffix="one")
        with pytest.raises(ValueError, match="dup"):
            self._insert(tmp_path, sandbox_id="dup", path_suffix="two")

        assert get_sandbox("dup", cwd=tmp_path, db_rel_path=DB_REL) is not None
        listed = list_sandboxes(cwd=tmp_path, db_rel_path=DB_REL)
        assert len(listed) == 1

    def test_get_sandbox_missing_returns_none(self, tmp_path: Path) -> None:
        assert get_sandbox("missing", cwd=tmp_path, db_rel_path=DB_REL) is None

    def test_list_sandboxes_order_and_filter(self, tmp_path: Path) -> None:
        first = self._insert(tmp_path, sandbox_id="sbx_first", path_suffix="1")
        time.sleep(1.1)
        second = self._insert(
            tmp_path, sandbox_id="sbx_second", path_suffix="2", name="beta"
        )
        update_sandbox_status(
            second.id,
            SandboxStatus.CLEANED,
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )

        all_rows = list_sandboxes(cwd=tmp_path, db_rel_path=DB_REL)
        assert [row.id for row in all_rows] == ["sbx_second", "sbx_first"]

        active = list_sandboxes(
            status=SandboxStatus.ACTIVE, cwd=tmp_path, db_rel_path=DB_REL
        )
        assert [row.id for row in active] == [first.id]

        cleaned = list_sandboxes(
            status=SandboxStatus.CLEANED, cwd=tmp_path, db_rel_path=DB_REL
        )
        assert [row.id for row in cleaned] == [second.id]

        empty = list_sandboxes(
            status=SandboxStatus.CONFLICT, cwd=tmp_path, db_rel_path=DB_REL
        )
        assert empty == []

    def test_list_sandboxes_empty(self, tmp_path: Path) -> None:
        assert list_sandboxes(cwd=tmp_path, db_rel_path=DB_REL) == []

    def test_update_sandbox_status(self, tmp_path: Path) -> None:
        created = self._insert(tmp_path)
        original_updated = created.updated_at
        time.sleep(1.1)

        updated = update_sandbox_status(
            created.id,
            SandboxStatus.MERGED,
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        assert updated is not None
        assert updated.status is SandboxStatus.MERGED
        assert updated.updated_at != original_updated
        assert updated.created_at == created.created_at

        loaded = get_sandbox(created.id, cwd=tmp_path, db_rel_path=DB_REL)
        assert loaded is not None
        assert loaded.status is SandboxStatus.MERGED

    def test_update_sandbox_status_missing(self, tmp_path: Path) -> None:
        assert (
            update_sandbox_status(
                "missing",
                SandboxStatus.CLEANED,
                cwd=tmp_path,
                db_rel_path=DB_REL,
            )
            is None
        )

    def test_delete_sandbox_row(self, tmp_path: Path) -> None:
        created = self._insert(tmp_path)
        assert delete_sandbox_row(created.id, cwd=tmp_path, db_rel_path=DB_REL)
        assert get_sandbox(created.id, cwd=tmp_path, db_rel_path=DB_REL) is None
        assert not delete_sandbox_row(created.id, cwd=tmp_path, db_rel_path=DB_REL)

    def test_helpers_auto_init_database(self, tmp_path: Path) -> None:
        created = insert_sandbox(
            id="sbx_auto",
            branch_name="worktree/sandbox-sbx_auto",
            base_commit="deadbeef",
            sandbox_path=tmp_path / "sandboxes" / "auto",
            cwd=tmp_path,
            db_rel_path=DB_REL,
        )
        assert created.status is SandboxStatus.ACTIVE
        assert (tmp_path / DB_REL).is_file()
