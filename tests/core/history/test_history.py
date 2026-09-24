"""Tier 1 domain tests for History entrypoint coordinator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from worktree.core.db import RunRecord, RunsRepository, RunStatus
from worktree.core.db.connection import resolve_db_path
from worktree.core.engine.models import ReconciliationResult
from worktree.core.history import History
from worktree.core.history.models import (
    HistoryListStatus,
    HistoryShowStatus,
)


def _as_expected_record(record: RunRecord) -> RunRecord:
    """Construct an explicit expected RunRecord instance with all model fields set."""
    return RunRecord.model_construct(
        id=record.id,
        project_id=record.project_id,
        session_id=record.session_id,
        blueprint_key=record.blueprint_key,
        blueprint_name=record.blueprint_name,
        branch_name=record.branch_name,
        status=record.status,
        pid=record.pid,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error_message=record.error_message,
        checkpoint_json=record.checkpoint_json,
    )


class HistoryInitializationTests:
    """Unit tests for History class constructor and dependency defaults."""

    def test_default_initialization_constructs_runs_repository_from_resolved_path(
        self, isolated_workspace: Path
    ) -> None:
        """[tier-1/unit] History.__init__: omitting db argument initializes RunsRepository with resolved path."""
        history = History(path=isolated_workspace)

        assert history.path == isolated_workspace.resolve()
        assert history.cwd == isolated_workspace.resolve()
        assert isinstance(history.db, RunsRepository)
        assert history.db.db_path == resolve_db_path()


class HistoryListTests:
    """Integration tests for History.list querying and reconciliation."""

    def test_empty_database_returns_ok_status_with_empty_runs(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.list: empty runs table returns HistoryListResult with status=OK, runs=[], warnings=[]."""
        history = History(isolated_workspace)

        result = history.list()

        assert result.status == HistoryListStatus.OK
        assert result.runs == []
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True

    def test_unfiltered_list_returns_runs_ordered_with_ok_status(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.list: returns all runs up to default limit with status=OK in descending order."""
        history = History(isolated_workspace)
        run_first = history.db.create(
            session_id="session-001",
            blueprint_name="task-alpha",
            blueprint_key="task-alpha",
            status=RunStatus.COMPLETED,
        )
        run_second = history.db.create(
            session_id="session-002",
            blueprint_name="task-beta",
            blueprint_key="task-beta",
            status=RunStatus.FAILED,
        )

        result = history.list()

        assert result.status == HistoryListStatus.OK
        assert result.runs == [_as_expected_record(run_second), _as_expected_record(run_first)]
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True

    def test_limit_parameter_restricts_number_of_returned_runs(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.list: limit=N restricts returned runs to N records."""
        history = History(isolated_workspace)
        history.db.create(
            session_id="session-001",
            blueprint_name="task-alpha",
            blueprint_key="task-alpha",
            status=RunStatus.COMPLETED,
        )
        history.db.create(
            session_id="session-002",
            blueprint_name="task-beta",
            blueprint_key="task-beta",
            status=RunStatus.COMPLETED,
        )
        run_third = history.db.create(
            session_id="session-003",
            blueprint_name="task-gamma",
            blueprint_key="task-gamma",
            status=RunStatus.COMPLETED,
        )

        result = history.list(limit=1)

        assert result.status == HistoryListStatus.OK
        assert result.runs == [_as_expected_record(run_third)]
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True

    @pytest.mark.parametrize(
        ("status_arg", "expected_session_id"),
        [
            pytest.param("completed", "session-comp", id="lowercase-completed"),
            pytest.param("COMPLETED", "session-comp", id="uppercase-completed"),
            pytest.param("failed", "session-fail", id="lowercase-failed"),
            pytest.param("FAILED", "session-fail", id="uppercase-failed"),
            pytest.param("running", "session-run", id="lowercase-running"),
        ],
    )
    def test_status_filter_filters_matching_runs(
        self, isolated_workspace: Path, status_arg: str, expected_session_id: str
    ) -> None:
        """[tier-1/integration] History.list: status filter correctly filters runs by status enum and case-insensitively."""
        history = History(isolated_workspace)
        run_comp = history.db.create(
            session_id="session-comp",
            blueprint_name="task-comp",
            blueprint_key="task-comp",
            status=RunStatus.COMPLETED,
        )
        run_fail = history.db.create(
            session_id="session-fail",
            blueprint_name="task-fail",
            blueprint_key="task-fail",
            status=RunStatus.FAILED,
        )
        # Using current process PID ensures is_run_stale is False so reconcile_stale_runs does not flip status to FAILED.
        run_active = history.db.create(
            session_id="session-run",
            blueprint_name="task-run",
            blueprint_key="task-run",
            status=RunStatus.RUNNING,
            pid=os.getpid(),
        )
        lookup: dict[str, RunRecord] = {
            "session-comp": run_comp,
            "session-fail": run_fail,
            "session-run": run_active,
        }

        result = history.list(status=status_arg)

        assert result.status == HistoryListStatus.OK
        assert result.runs == [_as_expected_record(lookup[expected_session_id])]
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True

    def test_unknown_status_filter_fallback_passes_raw_string_to_query(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.list: invalid status string falls back to raw string filter without raising ValueError."""
        history = History(isolated_workspace)
        history.db.create(
            session_id="session-comp",
            blueprint_name="task-comp",
            blueprint_key="task-comp",
            status=RunStatus.COMPLETED,
        )

        result = history.list(status="nonexistent_status_value")

        assert result.status == HistoryListStatus.OK
        assert result.runs == []
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True

    def test_stale_run_reconciliation_warning_is_captured_in_result(
        self, isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[tier-1/integration] History.list: reconciliation warning from reconcile_stale_runs is appended to warnings."""
        history = History(isolated_workspace)

        def _mock_reconcile(*_args: object, **_kwargs: object) -> ReconciliationResult:
            return ReconciliationResult(reconciled=[], warning="Session was terminated abnormally")

        monkeypatch.setattr("worktree.core.history.history.reconcile_stale_runs", _mock_reconcile)

        result = history.list()

        assert result.status == HistoryListStatus.OK
        assert result.runs == []
        assert result.errors == []
        assert result.warnings == ["Session was terminated abnormally"]
        assert result.fixes == []
        assert result.ok is True


class HistoryShowTests:
    """Integration tests for History.show session lookup."""

    def test_missing_session_id_returns_not_found_status(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.show: missing session_id returns HistoryShowResult with status=NOT_FOUND and run=None."""
        history = History(isolated_workspace)

        result = history.show("nonexistent-session")

        assert result.status == HistoryShowStatus.NOT_FOUND
        assert result.session_id == "nonexistent-session"
        assert result.run is None
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is False

    def test_existing_session_id_returns_ok_status_with_run_record(self, isolated_workspace: Path) -> None:
        """[tier-1/integration] History.show: existing session_id returns HistoryShowResult with status=OK and run record."""
        history = History(isolated_workspace)
        seeded_run = history.db.create(
            session_id="session-alpha",
            blueprint_name="deploy-flow",
            blueprint_key="deploy-flow",
            status=RunStatus.COMPLETED,
        )

        result = history.show("session-alpha")

        assert result.status == HistoryShowStatus.OK
        assert result.session_id == "session-alpha"
        assert result.run == _as_expected_record(seeded_run)
        assert result.errors == []
        assert result.warnings == []
        assert result.fixes == []
        assert result.ok is True
