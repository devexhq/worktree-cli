"""Tests for SQLite token usage and sandbox metadata helpers."""

from __future__ import annotations

import sqlite3

import pytest

from tests.helpers import FileSystem
from worktree.core.db import (
    SandboxStatus,
    WorktreeDb,
    init_database,
)

DB_REL = ".worktree/data.db"


class DatabaseTests:
    """Tests for init/record/aggregate token usage."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_init_creates_db(self, fs: FileSystem) -> None:
        db_path = init_database(path=fs.base_path, db_rel_path=DB_REL)
        assert db_path.is_file()

        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "workflow_costs" in tables
        assert "sandboxes" in tables

    def test_init_is_idempotent(self, fs: FileSystem) -> None:
        first = init_database(path=fs.base_path, db_rel_path=DB_REL)
        second = init_database(path=fs.base_path, db_rel_path=DB_REL)
        assert first == second
        assert first.is_file()

    def test_record_and_aggregate(self, fs: FileSystem) -> None:
        row_id = self.db.costs.record_token_usage(
            session_id="s1",
            branch_name="feature",
            model_id="m",
            prompt_tokens=10,
            completion_tokens=5,
            estimated_usd_cost=0.01,
        )
        assert row_id is not None

        totals = self.db.costs.get_session_total_cost("s1")
        assert totals["total_prompt_tokens"] == 10
        assert totals["total_completion_tokens"] == 5
        assert totals["total_tokens"] == 15
        assert totals["total_usd_cost"] == pytest.approx(0.01)

    def test_empty_session_totals(self, fs: FileSystem) -> None:
        self.db.costs.init_db()
        totals = self.db.costs.get_session_total_cost("missing")
        assert totals["total_tokens"] == 0
        assert totals["total_usd_cost"] == 0.0


class SandboxDatabaseTests:
    """Tests for sandboxes table CRUD helpers."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def _insert(
        self,
        fs: FileSystem,
        *,
        sandbox_id: str = "sbx_a1b2c3d4",
        name: str | None = "alpha",
        path_suffix: str = "a",
    ):
        return self.db.sandboxes.insert(
            id=sandbox_id,
            branch_name=f"worktree/sandbox-{sandbox_id}",
            base_commit="abc123",
            sandbox_path=fs.base_path / ".worktree" / "sandboxes" / path_suffix,
            name=name,
        )

    def test_insert_and_get_sandbox(self, fs: FileSystem) -> None:
        created = self._insert(fs)
        assert created.id == "sbx_a1b2c3d4"
        assert created.name == "alpha"
        assert created.branch_name == "worktree/sandbox-sbx_a1b2c3d4"
        assert created.base_commit == "abc123"
        assert created.sandbox_path == (fs.base_path / ".worktree" / "sandboxes" / "a")
        assert created.status is SandboxStatus.ACTIVE
        assert created.created_at
        assert created.updated_at

        loaded = self.db.sandboxes.get("sbx_a1b2c3d4")
        assert loaded is not None
        assert loaded == created

    def test_insert_name_none_stores_null(self, fs: FileSystem) -> None:
        created = self._insert(fs, name=None)
        assert created.name is None
        loaded = self.db.sandboxes.get(created.id)
        assert loaded is not None
        assert loaded.name is None

    def test_insert_duplicate_id_raises(self, fs: FileSystem) -> None:
        self._insert(fs, sandbox_id="dup", path_suffix="one")
        with pytest.raises(ValueError, match="dup"):
            self._insert(fs, sandbox_id="dup", path_suffix="two")

        assert self.db.sandboxes.get("dup") is not None
        listed = self.db.sandboxes.list()
        assert len(listed) == 1

    def test_get_sandbox_missing_returns_none(self, fs: FileSystem) -> None:
        assert self.db.sandboxes.get("missing") is None

    def test_list_sandboxes_order_and_filter(self, fs: FileSystem) -> None:
        first = self._insert(fs, sandbox_id="sbx_first", path_suffix="1")
        second = self._insert(fs, sandbox_id="sbx_second", path_suffix="2", name="beta")
        import sqlite3

        with sqlite3.connect(self.db.sandboxes.db_path) as conn:
            conn.execute("UPDATE sandboxes SET created_at = '2026-01-01 00:00:00' WHERE id = ?", (first.id,))
            conn.execute("UPDATE sandboxes SET created_at = '2026-01-01 00:00:01' WHERE id = ?", (second.id,))
            conn.commit()
        self.db.sandboxes.update_status(second.id, SandboxStatus.CLEANED)

        all_rows = self.db.sandboxes.list()
        assert [row.id for row in all_rows] == ["sbx_second", "sbx_first"]

        active = self.db.sandboxes.list(status=SandboxStatus.ACTIVE)
        assert [row.id for row in active] == [first.id]

        cleaned = self.db.sandboxes.list(status=SandboxStatus.CLEANED)
        assert [row.id for row in cleaned] == [second.id]

        empty = self.db.sandboxes.list(status=SandboxStatus.CONFLICT)
        assert empty == []

    def test_list_sandboxes_empty(self, fs: FileSystem) -> None:
        assert self.db.sandboxes.list() == []

    def test_update_sandbox_status(self, fs: FileSystem) -> None:
        created = self._insert(fs)
        original_updated = created.updated_at
        import sqlite3

        with sqlite3.connect(self.db.sandboxes.db_path) as conn:
            conn.execute("UPDATE sandboxes SET updated_at = '2026-01-01 00:00:00' WHERE id = ?", (created.id,))
            conn.commit()
        original_updated = "2026-01-01 00:00:00"

        updated = self.db.sandboxes.update_status(created.id, SandboxStatus.MERGED)
        assert updated is not None
        assert updated.status == SandboxStatus.MERGED
        assert updated.updated_at != original_updated
        assert updated.created_at == created.created_at

        loaded = self.db.sandboxes.get(created.id)
        assert loaded is not None
        assert loaded.status == SandboxStatus.MERGED

    def test_update_sandbox_status_missing(self, fs: FileSystem) -> None:
        assert self.db.sandboxes.update_status("missing", SandboxStatus.CLEANED) is None

    def test_delete_sandbox_row(self, fs: FileSystem) -> None:
        created = self._insert(fs)
        assert self.db.sandboxes.delete(created.id)
        assert self.db.sandboxes.get(created.id) is None
        assert not self.db.sandboxes.delete(created.id)

    def test_helpers_auto_init_database(self, fs: FileSystem) -> None:
        created = self.db.sandboxes.insert(
            id="sbx_auto",
            branch_name="worktree/sandbox-sbx_auto",
            base_commit="deadbeef",
            sandbox_path=fs.base_path / "sandboxes" / "auto",
        )
        assert created.status is SandboxStatus.ACTIVE
        assert (fs.base_path / DB_REL).is_file()
