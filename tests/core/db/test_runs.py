"""Unit tests for RunsRepository."""

from __future__ import annotations

import pytest

from tests.helpers import FileSystem
from worktree.core.db import BlueprintKind, RunRecord, RunStatus, WorktreeDb

DB_REL = ".worktree/data.db"


class TestRunsRepository:
    """Tests for RunsRepository operations."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=DB_REL)

    def test_create_and_get(self, fs: FileSystem) -> None:
        rec = self.db.runs.create(
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
        assert rec.pid is None

        fetched = self.db.runs.get("run_1")
        assert fetched == rec

    def test_create_with_pid(self, fs: FileSystem) -> None:
        rec = self.db.runs.create(
            session_id="run_pid",
            blueprint_name="test_bp",
            kind=BlueprintKind.TASK,
            pid=12345,
        )
        assert rec.pid == 12345

        fetched = self.db.runs.get("run_pid")
        assert fetched is not None
        assert fetched.pid == 12345

        updated = self.db.runs.update_status("run_pid", status=RunStatus.RUNNING, pid=67890)
        assert updated is not None
        assert updated.pid == 67890

    def test_create_with_defaults_and_string_enums(self, fs: FileSystem) -> None:
        rec = self.db.runs.create(
            session_id="run_wf",
            blueprint_name="ship",
            kind="workflow",
        )

        assert rec.kind == BlueprintKind.WORKFLOW
        assert rec.branch_name == ""
        assert rec.status == RunStatus.RUNNING

    def test_create_duplicate_session_id_raises_value_error(self, fs: FileSystem) -> None:
        self.db.runs.create(session_id="dup_sid", blueprint_name="task1", kind=BlueprintKind.TASK)

        with pytest.raises(ValueError, match="already exists"):
            self.db.runs.create(session_id="dup_sid", blueprint_name="task2", kind=BlueprintKind.TASK)

    def test_get_missing_returns_none(self, fs: FileSystem) -> None:
        assert self.db.runs.get("missing_sid") is None

    def test_update_status_completed(self, fs: FileSystem) -> None:
        self.db.runs.create(session_id="run_complete", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = self.db.runs.update_status("run_complete", status=RunStatus.COMPLETED)
        assert updated is not None
        assert updated.status is RunStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.error_message is None

    def test_update_status_failed_with_error_and_explicit_completed_at(self, fs: FileSystem) -> None:
        self.db.runs.create(session_id="run_fail", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = self.db.runs.update_status(
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
        assert self.db.runs.update_status("nonexistent", status=RunStatus.COMPLETED) is None

    def test_update_status_invalid_constraint_raises_value_error(self, fs: FileSystem) -> None:
        self.db.runs.create(session_id="run_invalid", blueprint_name="task1", kind=BlueprintKind.TASK)

        with pytest.raises(ValueError, match="constraint"):
            self.db.runs.update_status("run_invalid", status="invalid_status")  # pyright: ignore[reportArgumentType]

    def test_save_pause(self, fs: FileSystem) -> None:
        self.db.runs.create(session_id="run_pause", blueprint_name="task1", kind=BlueprintKind.TASK)

        updated = self.db.runs.save_pause("run_pause", '{"step": 1}', error_message="Step 1 interrupted")
        assert updated is not None
        assert updated.status is RunStatus.PAUSED
        assert updated.completed_at is None
        assert updated.checkpoint_json == '{"step": 1}'
        assert updated.error_message == "Step 1 interrupted"

    def test_list_all_and_ordering(self, fs: FileSystem) -> None:
        self.db.runs.create("s1", "task1", BlueprintKind.TASK)
        self.db.runs.create("s2", "wf1", BlueprintKind.WORKFLOW)
        self.db.runs.create("s3", "task2", BlueprintKind.TASK)

        runs = self.db.runs.list()
        assert len(runs) == 3
        # Ordered by started_at DESC, id DESC
        assert [r.session_id for r in runs] == ["s3", "s2", "s1"]

    def test_list_filtering_by_status(self, fs: FileSystem) -> None:
        self.db.runs.create("s1", "task1", BlueprintKind.TASK, status=RunStatus.RUNNING)
        self.db.runs.create("s2", "task2", BlueprintKind.TASK, status=RunStatus.COMPLETED)
        self.db.runs.create("s3", "task3", BlueprintKind.TASK, status=RunStatus.RUNNING)

        running = self.db.runs.list(status=RunStatus.RUNNING)
        assert len(running) == 2
        assert {r.session_id for r in running} == {"s1", "s3"}

        completed = self.db.runs.list(status="completed")
        assert len(completed) == 1
        assert completed[0].session_id == "s2"

    def test_list_filtering_by_kind(self, fs: FileSystem) -> None:
        self.db.runs.create("task_1", "lint", BlueprintKind.TASK)
        self.db.runs.create("wf_1", "deploy", BlueprintKind.WORKFLOW)
        self.db.runs.create("task_2", "format", BlueprintKind.TASK)

        tasks = self.db.runs.list(kind=BlueprintKind.TASK)
        assert len(tasks) == 2
        assert {r.session_id for r in tasks} == {"task_1", "task_2"}

        workflows = self.db.runs.list(kind="workflow")
        assert len(workflows) == 1
        assert workflows[0].session_id == "wf_1"

    def test_list_with_limit(self, fs: FileSystem) -> None:
        for i in range(5):
            self.db.runs.create(f"s_{i}", f"task_{i}", BlueprintKind.TASK)

        limited = self.db.runs.list(limit=2)
        assert len(limited) == 2
        assert limited[0].session_id == "s_4"
        assert limited[1].session_id == "s_3"

    def test_get_latest_paused(self, fs: FileSystem) -> None:
        assert self.db.runs.get_latest_paused() is None

        self.db.runs.create("s1", "task1", BlueprintKind.TASK, status=RunStatus.RUNNING)
        self.db.runs.create("s2", "wf1", BlueprintKind.WORKFLOW, status=RunStatus.RUNNING)
        self.db.runs.save_pause("s1", '{"v": 1}')
        self.db.runs.save_pause("s2", '{"v": 2}')

        latest = self.db.runs.get_latest_paused()
        assert latest is not None
        assert latest.session_id == "s2"
        assert latest.status is RunStatus.PAUSED
