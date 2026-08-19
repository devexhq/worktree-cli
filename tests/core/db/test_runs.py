"""Unit tests for RunsDb repository."""

from __future__ import annotations

import pytest

from tests.helpers import FileSystem
from worktree.core.db import BlueprintKind, RunRecord, RunsDb, RunStatus

DB_REL = ".worktree/data.db"


class TestRunsDb:
    """Tests for RunsDb repository operations."""

    def test_create_and_get(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        rec = db.create(
            session_id="run_1",
            blueprint_name="lint",
            kind=BlueprintKind.TASK,
            branch_name="feature/lint",
            status=RunStatus.RUNNING,
        )

        assert isinstance(rec, RunRecord)
        assert rec.id == 1
        assert rec.session_id == "run_1"
        assert rec.blueprint_name == "lint"
        assert rec.kind == BlueprintKind.TASK
        assert rec.branch_name == "feature/lint"
        assert rec.status is RunStatus.RUNNING
        assert rec.started_at
        assert rec.completed_at is None
        assert rec.error_message is None
        assert rec.checkpoint_json is None

        fetched = db.get("run_1")
        assert fetched == rec

    def test_create_with_defaults_and_string_enums(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        rec = db.create(
            session_id="run_wf",
            blueprint_name="ship",
            kind="workflow",
        )

        assert rec.kind == BlueprintKind.WORKFLOW
        assert rec.branch_name == ""
        assert rec.status == RunStatus.RUNNING

    def test_create_duplicate_session_id_raises_value_error(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create(session_id="dup_sid", blueprint_name="task1", kind=BlueprintKind.TASK)

        with pytest.raises(ValueError, match="already exists"):
            db.create(session_id="dup_sid", blueprint_name="task2", kind=BlueprintKind.TASK)

    def test_get_missing_returns_none(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get("missing_sid") is None

    def test_update_status_completed(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create(session_id="run_complete", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = db.update_status("run_complete", status=RunStatus.COMPLETED)
        assert updated is not None
        assert updated.status is RunStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.error_message is None

    def test_update_status_failed_with_error_and_explicit_completed_at(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create(session_id="run_fail", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = db.update_status(
            "run_fail",
            status=RunStatus.FAILED,
            error_message="Step failed: syntax error",
            completed_at="2026-01-01 12:00:00",
        )
        assert updated is not None
        assert updated.status is RunStatus.FAILED
        assert updated.completed_at == "2026-01-01 12:00:00"
        assert updated.error_message == "Step failed: syntax error"

    def test_update_status_missing_returns_none(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.update_status("nonexistent", status=RunStatus.COMPLETED) is None

    def test_update_status_invalid_constraint_raises_value_error(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create(session_id="run_invalid", blueprint_name="task1", kind=BlueprintKind.TASK)

        with pytest.raises(ValueError, match="constraint"):
            db.update_status("run_invalid", status="invalid_status")  # type: ignore[arg-type]

    def test_save_pause(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create(session_id="run_pause", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = db.save_pause("run_pause", '{"step": 1}', error_message="Step 1 interrupted")
        assert updated is not None
        assert updated.status is RunStatus.PAUSED
        assert updated.completed_at is None
        assert updated.checkpoint_json == '{"step": 1}'
        assert updated.error_message == "Step 1 interrupted"

    def test_list_all_and_ordering(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create("s1", "task1", BlueprintKind.TASK)
        db.create("s2", "wf1", BlueprintKind.WORKFLOW)
        db.create("s3", "task2", BlueprintKind.TASK)

        runs = db.list()
        assert len(runs) == 3
        # Ordered by started_at DESC, id DESC
        assert [r.session_id for r in runs] == ["s3", "s2", "s1"]

    def test_list_filtering_by_status(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create("s1", "task1", BlueprintKind.TASK, status=RunStatus.RUNNING)
        db.create("s2", "task2", BlueprintKind.TASK, status=RunStatus.COMPLETED)
        db.create("s3", "task3", BlueprintKind.TASK, status=RunStatus.RUNNING)

        running = db.list(status=RunStatus.RUNNING)
        assert len(running) == 2
        assert {r.session_id for r in running} == {"s1", "s3"}

        completed = db.list(status="completed")
        assert len(completed) == 1
        assert completed[0].session_id == "s2"

    def test_list_filtering_by_kind(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        db.create("task_1", "lint", BlueprintKind.TASK)
        db.create("wf_1", "deploy", BlueprintKind.WORKFLOW)
        db.create("task_2", "format", BlueprintKind.TASK)

        tasks = db.list(kind=BlueprintKind.TASK)
        assert len(tasks) == 2
        assert {r.session_id for r in tasks} == {"task_1", "task_2"}

        workflows = db.list(kind="workflow")
        assert len(workflows) == 1
        assert workflows[0].session_id == "wf_1"

    def test_list_with_limit(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        for i in range(5):
            db.create(f"s_{i}", f"task_{i}", BlueprintKind.TASK)

        limited = db.list(limit=2)
        assert len(limited) == 2
        assert limited[0].session_id == "s_4"
        assert limited[1].session_id == "s_3"

    def test_get_latest_paused(self, fs: FileSystem) -> None:
        db = RunsDb(cwd=fs.base_path, db_rel_path=DB_REL)
        assert db.get_latest_paused() is None

        db.create("s1", "task1", BlueprintKind.TASK, status=RunStatus.RUNNING)
        db.create("s2", "wf1", BlueprintKind.WORKFLOW, status=RunStatus.RUNNING)
        db.save_pause("s1", '{"v": 1}')
        db.save_pause("s2", '{"v": 2}')

        latest = db.get_latest_paused()
        assert latest is not None
        assert latest.session_id == "s2"
        assert latest.status is RunStatus.PAUSED
