"""Tests for session reconciliation, process liveness checks, and PID tracking."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from tests.helpers import FileSystem
from worktree.core.db import BlueprintKind, RunRecord, RunStatus, WorktreeDb
from worktree.core.engine.services.reconcile import (
    STALE_RUN_ERROR_MESSAGE,
    _parse_timestamp,
    format_reconciliation_warning,
    get_process_start_time,
    is_pid_alive,
    is_run_stale,
    reconcile_stale_runs,
)

DEAD_PID = 9999999


class TestProcessLiveness:
    """Tests for low-level process liveness detection and process start time lookup."""

    def test_is_pid_alive_current_process(self) -> None:
        assert is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_dead_process(self) -> None:
        assert is_pid_alive(DEAD_PID) is False

    def test_is_pid_alive_invalid_pids(self) -> None:
        assert is_pid_alive(0) is False
        assert is_pid_alive(-1) is False

    def test_get_process_start_time_current_process(self) -> None:
        start_time = get_process_start_time(os.getpid())
        # Start time should be inspectable on supported platforms or None on un-inspectable
        if start_time is not None:
            assert isinstance(start_time, datetime)
            assert start_time <= datetime.now(UTC)

    def test_get_process_start_time_invalid_pids(self) -> None:
        assert get_process_start_time(0) is None
        assert get_process_start_time(-1) is None
        assert get_process_start_time(DEAD_PID) is None

    def test_parse_timestamp_formats(self) -> None:
        standard = _parse_timestamp("2026-08-30 12:00:00")
        assert standard is not None
        assert standard.tzinfo == UTC
        assert standard.year == 2026

        iso = _parse_timestamp("2026-08-30T12:00:00Z")
        assert iso is not None

        invalid = _parse_timestamp("invalid-date")
        assert invalid is None


class TestIsRunStale:
    """Tests for run record staleness classification logic."""

    def test_completed_or_failed_run_not_stale(self) -> None:
        completed_run = RunRecord(
            session_id="s_comp",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
            pid=DEAD_PID,
        )
        assert is_run_stale(completed_run) is False

        failed_run = RunRecord(
            session_id="s_fail",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.FAILED,
            pid=DEAD_PID,
        )
        assert is_run_stale(failed_run) is False

    def test_running_run_none_pid_is_stale(self) -> None:
        orphan_run = RunRecord(
            session_id="s_orphan",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=None,
        )
        assert is_run_stale(orphan_run) is True

    def test_running_run_dead_pid_is_stale(self) -> None:
        dead_run = RunRecord(
            session_id="s_dead",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=DEAD_PID,
        )
        assert is_run_stale(dead_run) is True

    def test_running_run_active_pid_not_stale(self) -> None:
        active_run = RunRecord(
            session_id="s_active",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=os.getpid(),
            started_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        # For current PID without prior timestamp mismatch, not stale
        assert is_run_stale(active_run, current_pid=os.getpid()) is False

    def test_running_run_reused_pid_is_stale(self) -> None:
        old_session_start = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        reused_run = RunRecord(
            session_id="s_reused",
            blueprint_name="bp",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=12345,
            started_at=old_session_start,
        )

        with (
            patch("worktree.core.engine.services.reconcile.is_pid_alive", return_value=True),
            patch(
                "worktree.core.engine.services.reconcile.get_process_start_time",
                return_value=datetime.now(UTC) - timedelta(minutes=10),
            ),
        ):
            assert is_run_stale(reused_run) is True


class TestReconcileStaleRuns:
    """Tests for reconcile_stale_runs database transactions."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_db(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path, db_rel_path=".worktree/data.db")

    def test_reconcile_single_stale_run(self) -> None:
        self.db.runs.create(
            session_id="stale_1",
            blueprint_name="task_stale",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=DEAD_PID,
        )

        reconciled = reconcile_stale_runs(self.db)
        assert len(reconciled) == 1
        assert reconciled[0].session_id == "stale_1"
        assert reconciled[0].status == RunStatus.FAILED
        assert reconciled[0].error_message == STALE_RUN_ERROR_MESSAGE
        assert reconciled[0].completed_at is not None

        persisted = self.db.runs.get("stale_1")
        assert persisted is not None
        assert persisted.status == RunStatus.FAILED
        assert persisted.error_message == STALE_RUN_ERROR_MESSAGE

    def test_reconcile_with_runs_repository_instance(self, fs: FileSystem) -> None:
        self.db.runs.create(
            session_id="stale_repo",
            blueprint_name="task_stale",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=DEAD_PID,
        )

        reconciled = reconcile_stale_runs(self.db.runs, path=fs.base_path)
        assert len(reconciled) == 1
        assert reconciled[0].session_id == "stale_repo"
        assert reconciled[0].status == RunStatus.FAILED

    def test_reconcile_leaves_active_and_completed_runs_intact(self) -> None:
        self.db.runs.create(
            session_id="run_comp",
            blueprint_name="task1",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
            pid=DEAD_PID,
        )
        self.db.runs.create(
            session_id="run_active",
            blueprint_name="task2",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=os.getpid(),
        )

        reconciled = reconcile_stale_runs(self.db)
        assert len(reconciled) == 0

        comp_rec = self.db.runs.get("run_comp")
        active_rec = self.db.runs.get("run_active")
        assert comp_rec is not None
        assert comp_rec.status == RunStatus.COMPLETED
        assert active_rec is not None
        assert active_rec.status == RunStatus.RUNNING

    def test_reconcile_multiple_stale_runs(self) -> None:
        self.db.runs.create(
            session_id="stale_a",
            blueprint_name="task_a",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=DEAD_PID,
        )
        self.db.runs.create(
            session_id="stale_b",
            blueprint_name="task_b",
            kind=BlueprintKind.TASK,
            status=RunStatus.RUNNING,
            pid=None,
        )

        reconciled = reconcile_stale_runs(self.db)
        assert len(reconciled) == 2
        reconciled_ids = {r.session_id for r in reconciled}
        assert reconciled_ids == {"stale_a", "stale_b"}

    def test_format_reconciliation_warning(self) -> None:
        assert format_reconciliation_warning([]) is None

        r1 = RunRecord(session_id="s1", blueprint_name="bp", kind=BlueprintKind.TASK, status=RunStatus.FAILED)
        msg1 = format_reconciliation_warning([r1])
        assert msg1 == "Reconciled 1 interrupted session (session_id: s1)."

        r2 = RunRecord(session_id="s2", blueprint_name="bp", kind=BlueprintKind.TASK, status=RunStatus.FAILED)
        msg2 = format_reconciliation_warning([r1, r2])
        assert msg2 == "Reconciled 2 interrupted sessions (s1, s2)."
