"""Tests for SQLite database tables, DbBase, repository classes, and WorktreeDb facade."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.db import (
    BlueprintKind,
    CatalogItemType,
    CatalogRecord,
    CatalogRepository,
    DbBase,
    RunRecord,
    RunsRepository,
    RunStatus,
    SandboxesRepository,
    SandboxRecord,
    WorktreeDb,
    init_database,
)
from worktree.core.db.models import SandboxStatus

DB_REL = ".worktree/data.db"


class TestDatabaseMigrations:
    """Tests for database initialization and schema creation."""

    def test_init_creates_tables_and_indexes(self, fs: FileSystem) -> None:
        db_path = init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db_path.is_file()

        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}

        assert "catalog" in tables
        assert "sandboxes" in tables
        assert "workflow_costs" in tables
        assert "runs" in tables

        assert "idx_catalog_sha" in indexes
        assert "idx_catalog_type" in indexes
        assert "idx_catalog_path" in indexes
        assert "idx_runs_session" in indexes
        assert "idx_runs_status" in indexes
        assert "idx_runs_started" in indexes

    def test_init_is_idempotent(self, fs: FileSystem) -> None:
        path1 = init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        path2 = init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        assert path1 == path2
        assert path1.is_file()

    def test_init_migrates_legacy_run_tables_to_runs(self, fs: FileSystem) -> None:
        db_path = fs.base_path / DB_REL
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    workflow_name TEXT NOT NULL,
                    branch_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    checkpoint_json TEXT
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    checkpoint_json TEXT
                );
                INSERT INTO workflows (session_id, workflow_name, branch_name, status, checkpoint_json)
                VALUES ('wf_legacy', 'demo-wf', 'feat/w', 'paused', '{"v": 1}');
                INSERT INTO tasks (session_id, task_name, status)
                VALUES ('task_legacy', 'demo-task', 'completed');
                """
            )

        init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        db = RunsRepository(cwd=fs.base_path, db_rel_path=DB_REL)

        wf = db.get("wf_legacy")
        assert wf is not None
        assert wf.blueprint_name == "demo-wf"
        assert wf.kind == BlueprintKind.WORKFLOW
        assert wf.branch_name == "feat/w"
        assert wf.status == RunStatus.PAUSED
        assert wf.checkpoint_json == '{"v": 1}'

        tk = db.get("task_legacy")
        assert tk is not None
        assert tk.blueprint_name == "demo-task"
        assert tk.kind == BlueprintKind.TASK
        assert tk.status == RunStatus.COMPLETED


class TestDbBase:
    """Tests for DbBase core path resolution, cursor management, and helper methods."""

    def test_db_path_resolution(self, fs: FileSystem) -> None:
        db_base = DbBase(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db_base.db_path == fs.base_path / DB_REL

        custom_path = fs.base_path / "custom.db"
        db_base_custom = DbBase(db_path=custom_path)
        assert db_base_custom.db_path == custom_path

    def test_cursor_and_transaction(self, fs: FileSystem) -> None:
        db_base = DbBase(cwd=fs.base_path, db_rel_path=DB_REL)
        assert (
            db_base.execute_insert(
                "INSERT INTO runs (session_id, blueprint_name, kind) VALUES (?, ?, ?);",
                ("s1", "t1", "task"),
            )
            == 1
        )

        row = db_base.fetch_one("SELECT * FROM runs WHERE session_id = ?;", ("s1",))
        assert row is not None
        assert row["blueprint_name"] == "t1"

        all_rows = db_base.fetch_all("SELECT * FROM runs;")
        assert len(all_rows) == 1

    def test_transaction_rollback_on_exception(self, fs: FileSystem) -> None:
        db_base = DbBase(cwd=fs.base_path, db_rel_path=DB_REL)
        db_base.init_db()

        with pytest.raises(sqlite3.IntegrityError):
            with db_base.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO runs (session_id, blueprint_name, kind) VALUES (?, ?, ?);", ("s_dup", "t1", "task")
                )
                cursor.execute(
                    "INSERT INTO runs (session_id, blueprint_name, kind) VALUES (?, ?, ?);", ("s_dup", "t2", "task")
                )

        assert db_base.fetch_one("SELECT * FROM runs WHERE session_id = ?;", ("s_dup",)) is None


class TestSandboxesRepository:
    """Tests for SandboxesRepository CRUD methods."""

    def test_insert_and_get(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        sb = db.insert(
            id="sb-001",
            branch_name="feat/branch",
            base_commit="abc123",
            sandbox_path=fs.base_path / "sb-001",
        )

        assert isinstance(sb, SandboxRecord)
        assert sb.id == "sb-001"
        assert sb.branch_name == "feat/branch"
        assert sb.base_commit == "abc123"
        assert sb.sandbox_path == fs.base_path / "sb-001"
        assert sb.status == SandboxStatus.ACTIVE
        assert sb.name is None
        assert sb.created_at
        assert sb.updated_at

        fetched = db.get("sb-001")
        assert fetched == sb

    def test_insert_with_name(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        sb = db.insert(
            id="sb-named",
            branch_name="feat/named",
            base_commit="def456",
            sandbox_path=fs.base_path / "sb-named",
            name="my-sandbox",
        )
        assert sb.name == "my-sandbox"

    def test_insert_duplicate_raises_value_error(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(id="dup-id", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "dup")
        with pytest.raises(ValueError, match="dup-id"):
            db.insert(id="dup-id", branch_name="b2", base_commit="c2", sandbox_path=fs.base_path / "dup2")

    def test_get_missing_returns_none(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get("does-not-exist") is None

    def test_list_unfiltered_and_filtered(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(id="a", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "a")
        db.insert(id="b", branch_name="b2", base_commit="c2", sandbox_path=fs.base_path / "b")
        db.update_status("b", SandboxStatus.MERGED)

        all_rows = db.list()
        assert len(all_rows) == 2

        active = db.list(status=SandboxStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].id == "a"

        merged = db.list(status=SandboxStatus.MERGED)
        assert len(merged) == 1
        assert merged[0].id == "b"

    def test_update_status(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        sb = db.insert(id="upd", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "upd")
        original_updated_at = sb.updated_at

        updated = db.update_status("upd", SandboxStatus.CLEANED)
        assert updated is not None
        assert updated.status == SandboxStatus.CLEANED
        assert updated.updated_at >= original_updated_at

    def test_update_status_missing_returns_none(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.update_status("ghost", SandboxStatus.CLEANED) is None

    def test_delete(self, fs: FileSystem) -> None:
        db = SandboxesRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(id="del-me", branch_name="b", base_commit="c", sandbox_path=fs.base_path / "del-me")

        assert db.delete("del-me") is True
        assert db.get("del-me") is None
        assert db.delete("del-me") is False


class TestCatalogRepository:
    """Tests for CatalogRepository repository methods."""

    def test_upsert_insert_and_get_by_sha_and_name(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        path = Path(".worktree/catalog/workflow_a.yaml")
        rec = db.upsert(
            sha="workflow_1234567",
            item_type=CatalogItemType.WORKFLOW,
            name="workflow_a",
            path=path,
            checksum="hash1",
        )

        assert isinstance(rec, CatalogRecord)
        assert rec.id == 1
        assert rec.sha == "workflow_1234567"
        assert rec.item_type == CatalogItemType.WORKFLOW
        assert rec.name == "workflow_a"
        assert rec.path == path
        assert rec.checksum == "hash1"
        assert rec.created_at
        assert rec.updated_at

        by_sha = db.get_by_sha("workflow_1234567")
        assert by_sha == rec

        by_name = db.get_by_name("workflow_a")
        assert by_name == rec

        by_name_and_type = db.get_by_name(
            "workflow_a",
            item_type=CatalogItemType.WORKFLOW,
        )
        assert by_name_and_type == rec

    def test_upsert_update_preserves_id_and_updates_fields(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        path = Path(".worktree/catalog/task_b.yaml")
        first = db.upsert(
            sha="task_1111111",
            item_type=CatalogItemType.TASK,
            name="task_b",
            path=path,
            checksum="chk1",
        )
        first_id = first.id
        first_created_at = first.created_at

        second = db.upsert(
            sha="task_2222222",
            item_type=CatalogItemType.TASK,
            name="task_b_v2",
            path=path,
            checksum="chk2",
        )

        assert second.id == first_id
        assert second.sha == "task_2222222"
        assert second.name == "task_b_v2"
        assert second.path == path
        assert second.checksum == "chk2"
        assert second.created_at == first_created_at

    def test_get_missing_catalog_item_returns_none(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get_by_sha("missing") is None
        assert db.get_by_name("missing_name") is None

    def test_list_catalog_items_filtering(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.upsert(sha="w1", item_type=CatalogItemType.WORKFLOW, name="wf1", path=Path("w1.yaml"), checksum="c1")
        db.upsert(sha="t1", item_type=CatalogItemType.TASK, name="task1", path=Path("t1.yaml"), checksum="c2")
        db.upsert(sha="s1", item_type=CatalogItemType.STEP, name="step1", path=Path("s1.yaml"), checksum="c3")

        all_items = db.list()
        assert len(all_items) == 3

        workflows = db.list(item_type=CatalogItemType.WORKFLOW)
        assert len(workflows) == 1
        assert workflows[0].sha == "w1"

        steps = db.list(item_type="step")
        assert len(steps) == 1
        assert steps[0].sha == "s1"

    def test_list_by_name(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.upsert(
            sha="n1", item_type=CatalogItemType.WORKFLOW, name="shared", path=Path("a/shared.yaml"), checksum="c1"
        )
        db.upsert(sha="n2", item_type=CatalogItemType.TASK, name="shared", path=Path("b/shared.yaml"), checksum="c2")

        all_shared = db.list_by_name("shared")
        assert len(all_shared) == 2

        wf_shared = db.list_by_name("shared", item_type=CatalogItemType.WORKFLOW)
        assert len(wf_shared) == 1
        assert wf_shared[0].sha == "n1"

    def test_invalid_catalog_item_type_raises_value_error(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        with pytest.raises(ValueError, match="constraint"):
            db.upsert(
                sha="invalid",
                item_type="invalid_type",  # type: ignore[arg-type]
                name="invalid",
                path=Path("invalid.yaml"),
                checksum="c",
            )

    def test_delete_catalog_item(self, fs: FileSystem) -> None:
        db = CatalogRepository(cwd=fs.base_path, db_rel_path=DB_REL)
        db.upsert(
            sha="to_delete",
            item_type=CatalogItemType.WORKFLOW,
            name="delete_item",
            path=Path("delete.yaml"),
            checksum="c_del",
        )

        assert db.delete("to_delete") is True
        assert db.get_by_sha("to_delete") is None
        assert db.delete("to_delete") is False


class TestWorktreeDbFacade:
    """Tests for WorktreeDb unified facade."""

    def test_facade_sub_repository_access(self, fs: FileSystem) -> None:
        db = WorktreeDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.init_db()

        sb = db.sandboxes.insert(
            id="sb_facade",
            branch_name="feat/facade",
            base_commit="abc",
            sandbox_path=fs.base_path / "sb_facade",
        )
        assert db.sandboxes.get("sb_facade") == sb

        run = db.runs.create(
            session_id="run_facade",
            blueprint_name="demo",
            kind=BlueprintKind.WORKFLOW,
            branch_name="b",
        )
        assert isinstance(run, RunRecord)
        assert db.runs.get("run_facade") == run

        cat = db.catalog.upsert(
            sha="c_facade",
            item_type=CatalogItemType.WORKFLOW,
            name="wf_cat",
            path=Path("wf_cat.yaml"),
            checksum="c",
        )
        assert db.catalog.get_by_sha("c_facade") == cat

        cost_id = db.costs.record_token_usage(
            session_id="run_facade",
            branch_name="b",
            model_id="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            estimated_usd_cost=0.005,
        )
        assert cost_id is not None
        totals = db.costs.get_session_total_cost("run_facade")
        assert totals["total_tokens"] == 30
