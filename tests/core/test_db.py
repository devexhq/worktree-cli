"""Tests for SQLite database tables, DbBase, repository classes, and WorktreeDb facade."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.helpers import FileSystem
from worktree.core.db import (
    CatalogDb,
    CatalogItemType,
    CatalogRecord,
    DbBase,
    RunStatus,
    RunTrackingDb,
    TaskRunRecord,
    TasksDb,
    WorkflowRunRecord,
    WorkflowsDb,
    WorktreeDb,
    init_database,
)

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
        assert "workflows" in tables
        assert "tasks" in tables

        assert "idx_catalog_sha" in indexes
        assert "idx_catalog_type" in indexes
        assert "idx_catalog_path" in indexes
        assert "idx_workflows_session" in indexes
        assert "idx_workflows_status" in indexes
        assert "idx_tasks_session" in indexes
        assert "idx_tasks_status" in indexes

    def test_init_is_idempotent(self, fs: FileSystem) -> None:
        path1 = init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        path2 = init_database(cwd=fs.base_path, db_rel_path=DB_REL)
        assert path1 == path2
        assert path1.is_file()


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
        assert db_base.execute_insert("INSERT INTO tasks (session_id, task_name) VALUES (?, ?);", ("s1", "t1")) == 1

        row = db_base.fetch_one("SELECT * FROM tasks WHERE session_id = ?;", ("s1",))
        assert row is not None
        assert row["task_name"] == "t1"

        all_rows = db_base.fetch_all("SELECT * FROM tasks;")
        assert len(all_rows) == 1

    def test_transaction_rollback_on_exception(self, fs: FileSystem) -> None:
        db_base = DbBase(cwd=fs.base_path, db_rel_path=DB_REL)
        db_base.init_db()

        with pytest.raises(sqlite3.IntegrityError):
            with db_base.cursor() as cursor:
                cursor.execute("INSERT INTO tasks (session_id, task_name) VALUES (?, ?);", ("s_dup", "t1"))
                cursor.execute("INSERT INTO tasks (session_id, task_name) VALUES (?, ?);", ("s_dup", "t2"))

        assert db_base.fetch_one("SELECT * FROM tasks WHERE session_id = ?;", ("s_dup",)) is None


class TestCatalogDb:
    """Tests for CatalogDb repository methods."""

    def test_upsert_insert_and_get_by_sha_and_name(self, fs: FileSystem) -> None:
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
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
        assert rec.item_type is CatalogItemType.WORKFLOW
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
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
        path = Path(".worktree/catalog/task_b.yaml")
        first = db.upsert(
            sha="task_1111111",
            item_type=CatalogItemType.TASK,
            name="task_b",
            path=path,
            checksum="chk1",
        )
        db.execute(
            "UPDATE catalog SET created_at = '2026-01-01 00:00:00', updated_at = '2026-01-01 00:00:00' WHERE id = ?",
            (first.id,),
        )
        first = db.get_by_sha("task_1111111")
        assert first is not None

        second = db.upsert(
            sha="task_2222222",
            item_type=CatalogItemType.TASK,
            name="task_b_v2",
            path=path,
            checksum="chk2",
        )

        assert second.id == first.id
        assert second.sha == "task_2222222"
        assert second.name == "task_b_v2"
        assert second.path == path
        assert second.checksum == "chk2"
        assert second.created_at == first.created_at
        assert second.updated_at != first.updated_at

    def test_get_missing_catalog_item_returns_none(self, fs: FileSystem) -> None:
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get_by_sha("missing") is None
        assert db.get_by_name("missing_name") is None

    def test_list_catalog_items_filtering(self, fs: FileSystem) -> None:
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.upsert(
            sha="w1",
            item_type=CatalogItemType.WORKFLOW,
            name="wf1",
            path=Path("w1.yaml"),
            checksum="c1",
        )
        db.upsert(
            sha="t1",
            item_type=CatalogItemType.TASK,
            name="task1",
            path=Path("t1.yaml"),
            checksum="c2",
        )
        db.upsert(
            sha="s1",
            item_type=CatalogItemType.STEP,
            name="step1",
            path=Path("s1.yaml"),
            checksum="c3",
        )

        all_items = db.list()
        assert len(all_items) == 3

        workflows = db.list(item_type=CatalogItemType.WORKFLOW)
        assert len(workflows) == 1
        assert workflows[0].sha == "w1"

        steps = db.list(item_type="step")
        assert len(steps) == 1
        assert steps[0].sha == "s1"

    def test_invalid_catalog_item_type_raises_value_error(self, fs: FileSystem) -> None:
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
        with pytest.raises(ValueError, match="constraint"):
            db.upsert(
                sha="invalid",
                item_type="invalid_type",  # type: ignore[arg-type]
                name="invalid",
                path=Path("invalid.yaml"),
                checksum="c",
            )

    def test_delete_catalog_item(self, fs: FileSystem) -> None:
        db = CatalogDb(cwd=fs.base_path, db_rel_path=DB_REL)
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


class DummyRunTrackingDb(RunTrackingDb[TaskRunRecord]):
    """Concrete subclass for testing generic RunTrackingDb behavior."""

    table = "tasks"
    record_cls = TaskRunRecord
    extra_columns = ("task_name",)


class TestRunTrackingDb:
    """Tests for RunTrackingDb generic base repository operations."""

    def test_insert_and_get(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        rec = db.insert("s1", status=RunStatus.RUNNING, task_name="dummy_task")

        assert isinstance(rec, TaskRunRecord)
        assert rec.session_id == "s1"
        assert rec.task_name == "dummy_task"
        assert rec.status is RunStatus.RUNNING

        fetched = db.get("s1")
        assert fetched == rec

    def test_insert_duplicate_session_id_raises_value_error(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert("s_dup", task_name="t1")

        with pytest.raises(ValueError, match="already exists"):
            db.insert("s_dup", task_name="t2")

    def test_insert_invalid_extra_columns_raises_value_error(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        with pytest.raises(ValueError, match="mismatched keys"):
            db.insert("s_bad", wrong_arg="val")  # type: ignore[call-arg]

    def test_get_missing_returns_none(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get("non_existent") is None

    def test_update_status(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert("s_upd", task_name="t_upd")

        updated = db.update_status("s_upd", status=RunStatus.COMPLETED, error_message=None)
        assert updated is not None
        assert updated.status is RunStatus.COMPLETED
        assert updated.completed_at is not None

    def test_update_status_missing_returns_none(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.update_status("missing", status=RunStatus.COMPLETED) is None

    def test_update_status_invalid_raises_value_error(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert("s_inv", task_name="t")

        with pytest.raises(ValueError, match="constraint"):
            db.update_status("s_inv", status="invalid_status")  # type: ignore[arg-type]

    def test_list(self, fs: FileSystem) -> None:
        db = DummyRunTrackingDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert("s_list1", task_name="t1")
        db.insert("s_list2", task_name="t2")

        runs = db.list()
        assert len(runs) == 2
        assert {r.session_id for r in runs} == {"s_list1", "s_list2"}


class TestWorkflowsDb:
    """Tests for WorkflowsDb repository methods."""

    def test_insert_and_get_workflow_run(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        rec = db.insert(
            session_id="wf_session_1",
            workflow_name="dev-workflow",
            branch_name="feature/workflow",
        )

        assert isinstance(rec, WorkflowRunRecord)
        assert rec.id == 1
        assert rec.session_id == "wf_session_1"
        assert rec.workflow_name == "dev-workflow"
        assert rec.branch_name == "feature/workflow"
        assert rec.status is RunStatus.RUNNING
        assert rec.started_at
        assert rec.completed_at is None
        assert rec.error_message is None

        fetched = db.get("wf_session_1")
        assert fetched == rec

    def test_insert_duplicate_session_id_raises_value_error(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="dup_wf",
            workflow_name="wf",
            branch_name="b",
        )

        with pytest.raises(ValueError, match="already exists"):
            db.insert(
                session_id="dup_wf",
                workflow_name="wf",
                branch_name="b",
            )

    def test_get_missing_workflow_run_returns_none(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get("non_existent") is None

    def test_update_workflow_run_status(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="wf_to_update",
            workflow_name="wf",
            branch_name="b",
        )

        updated = db.update_status(
            session_id="wf_to_update",
            status=RunStatus.FAILED,
            error_message="Execution timeout",
        )

        assert updated is not None
        assert updated.status is RunStatus.FAILED
        assert updated.completed_at is not None
        assert updated.error_message == "Execution timeout"

    def test_update_missing_workflow_run_returns_none(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.update_status(session_id="missing", status=RunStatus.COMPLETED) is None

    def test_invalid_workflow_status_raises_value_error(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="wf_invalid_status",
            workflow_name="wf",
            branch_name="b",
        )

        with pytest.raises(ValueError, match="constraint"):
            db.update_status(
                session_id="wf_invalid_status",
                status="invalid_status",  # type: ignore[arg-type]
            )

    def test_list_workflow_runs(self, fs: FileSystem) -> None:
        db = WorkflowsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="wf_1",
            workflow_name="wf1",
            branch_name="b1",
        )
        db.insert(
            session_id="wf_2",
            workflow_name="wf2",
            branch_name="b2",
        )

        runs = db.list()
        assert len(runs) == 2
        assert {r.session_id for r in runs} == {"wf_1", "wf_2"}


class TestTasksDb:
    """Tests for TasksDb repository methods."""

    def test_insert_and_get_task_run(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        rec = db.insert(
            session_id="task_session_1",
            task_name="lint-fix",
        )

        assert isinstance(rec, TaskRunRecord)
        assert rec.id == 1
        assert rec.session_id == "task_session_1"
        assert rec.task_name == "lint-fix"
        assert rec.status is RunStatus.RUNNING
        assert rec.started_at
        assert rec.completed_at is None
        assert rec.error_message is None

        fetched = db.get("task_session_1")
        assert fetched == rec

    def test_insert_duplicate_task_session_id_raises_value_error(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="dup_task",
            task_name="task",
        )

        with pytest.raises(ValueError, match="already exists"):
            db.insert(
                session_id="dup_task",
                task_name="task",
            )

    def test_get_missing_task_run_returns_none(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get("non_existent") is None

    def test_update_task_run_status(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="task_to_update",
            task_name="task",
        )

        updated = db.update_status(
            session_id="task_to_update",
            status=RunStatus.COMPLETED,
        )

        assert updated is not None
        assert updated.status is RunStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.error_message is None

    def test_update_missing_task_run_returns_none(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.update_status(session_id="missing", status=RunStatus.COMPLETED) is None

    def test_invalid_task_status_raises_value_error(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="task_invalid_status",
            task_name="task",
        )

        with pytest.raises(ValueError, match="constraint"):
            db.update_status(
                session_id="task_invalid_status",
                status="invalid_status",  # type: ignore[arg-type]
            )

    def test_list_task_runs(self, fs: FileSystem) -> None:
        db = TasksDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.insert(
            session_id="t_1",
            task_name="t1",
        )
        db.insert(
            session_id="t_2",
            task_name="t2",
        )

        runs = db.list()
        assert len(runs) == 2
        assert {r.session_id for r in runs} == {"t_1", "t_2"}


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

        wf = db.workflows.insert(
            session_id="wf_facade",
            workflow_name="wf",
            branch_name="b",
        )
        assert db.workflows.get("wf_facade") == wf

        tk = db.tasks.insert(
            session_id="tk_facade",
            task_name="tk",
        )
        assert db.tasks.get("tk_facade") == tk

        cat = db.catalog.upsert(
            sha="c_facade",
            item_type=CatalogItemType.WORKFLOW,
            name="wf_cat",
            path=Path("wf_cat.yaml"),
            checksum="c",
        )
        assert db.catalog.get_by_sha("c_facade") == cat

        cost_id = db.costs.record_token_usage(
            session_id="wf_facade",
            branch_name="b",
            model_id="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            estimated_usd_cost=0.005,
        )
        assert cost_id is not None
        totals = db.costs.get_session_total_cost("wf_facade")
        assert totals["total_tokens"] == 30
