"""Unit tests for HistoryListService and HistoryShowService."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FileSystem, RunFactory, make_run
from worktree.core.config.generator import generate_default_config
from worktree.core.db import RunStatus, WorktreeDb
from worktree.core.history.models import (
    HistoryListStatus,
    HistoryShowStatus,
)
from worktree.core.history.services import (
    HistoryListService,
    HistoryShowService,
)


def _init_workspace(root: Path) -> None:
    config_file = root / ".worktree" / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    generate_default_config(config_file, project_name="test")


class HistoryListServiceTests:
    """Direct unit tests for HistoryListService data collection and execution."""

    def test_collect_all_runs(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        make_run(
            worktree_db.runs,
            session_id="run-1",
            blueprint_name="task-1",
            blueprint_key="task-1",
            status=RunStatus.COMPLETED,
        )
        make_run(
            worktree_db.runs,
            session_id="run-2",
            blueprint_name="wf-1",
            blueprint_key="wf-1",
            status=RunStatus.FAILED,
        )

        service = HistoryListService(path=fs.base_path, db=worktree_db.runs)
        result = service.collect()
        assert result.ok
        assert result.status is HistoryListStatus.OK
        assert len(result.runs) == 2

    def test_collect_filter_by_status(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        make_run(
            worktree_db.runs,
            session_id="run-ok",
            blueprint_name="task-1",
            blueprint_key="task-1",
            status=RunStatus.COMPLETED,
        )
        make_run(
            worktree_db.runs,
            session_id="run-fail",
            blueprint_name="task-2",
            blueprint_key="task-2",
            status=RunStatus.FAILED,
        )

        # Status matching enum
        service = HistoryListService(path=fs.base_path, db=worktree_db.runs, status="failed")
        result = service.collect()
        assert result.ok
        assert len(result.runs) == 1
        assert result.runs[0].session_id == "run-fail"

        # Invalid status string fallback
        service_invalid = HistoryListService(path=fs.base_path, db=worktree_db.runs, status="nonexistent_status")
        result_invalid = service_invalid.collect()
        assert result_invalid.ok
        assert len(result_invalid.runs) == 0

    def test_collect_status_filter_includes_multiple_blueprint_kinds(
        self, fs: FileSystem, worktree_db: WorktreeDb
    ) -> None:
        make_run(
            worktree_db.runs,
            session_id="run-task",
            blueprint_name="task-1",
            blueprint_key="task-1",
            status=RunStatus.COMPLETED,
        )
        make_run(
            worktree_db.runs,
            session_id="run-wf",
            blueprint_name="wf-1",
            blueprint_key="wf-1",
            status=RunStatus.COMPLETED,
        )

        service = HistoryListService(path=fs.base_path, db=worktree_db.runs, status="completed")
        result = service.collect()
        assert result.ok
        assert {run.session_id for run in result.runs} == {"run-task", "run-wf"}

    def test_collect_limit(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        for i in range(5):
            make_run(
                worktree_db.runs,
                session_id=f"run-{i}",
                blueprint_name=f"task-{i}",
                blueprint_key=f"task-{i}",
                status=RunStatus.COMPLETED,
            )

        service = HistoryListService(path=fs.base_path, db=worktree_db.runs, limit=3)
        result = service.collect()
        assert result.ok
        assert len(result.runs) == 3

    def test_execute_renders_output(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        make_run(
            worktree_db.runs,
            session_id="run-exec",
            blueprint_name="sample-task",
            blueprint_key="sample-task",
            status=RunStatus.COMPLETED,
        )
        service = HistoryListService(path=fs.base_path, db=worktree_db.runs)
        result = service.execute()
        assert result.ok
        assert any(r.session_id == "run-exec" for r in result.runs)


class HistoryShowServiceTests:
    """Direct unit tests for HistoryShowService data collection and execution."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_collect_found(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        make_run(
            worktree_db.runs,
            session_id="run-show",
            blueprint_name="show-task",
            blueprint_key="show-task",
            status=RunStatus.COMPLETED,
        )

        service = HistoryShowService(session_id="run-show", path=fs.base_path, db=worktree_db.runs)
        result = service.collect()
        assert result.ok
        assert result.status is HistoryShowStatus.OK
        assert result.run is not None
        assert result.run.session_id == "run-show"

    def test_collect_not_found(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        _init_workspace(fs.base_path)
        service = HistoryShowService(session_id="missing-session", path=fs.base_path, db=worktree_db.runs)
        result = service.collect()
        assert not result.ok
        assert result.status is HistoryShowStatus.NOT_FOUND
        assert result.run is None

    def test_execute_found_renders_metadata(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        completed_run = RunFactory(worktree_db.runs).create(
            session_id="run-show-exec",
            blueprint_name="show-task",
            blueprint_key="show-task",
            status=RunStatus.COMPLETED,
        )

        service = HistoryShowService(session_id=completed_run.session_id, path=fs.base_path, db=worktree_db.runs)
        result = service.execute()
        assert result.ok
        assert result.run is not None
        assert result.run.session_id == completed_run.session_id
        assert result.run.blueprint_name == completed_run.blueprint_name

    def test_execute_not_found_renders_panel(self, fs: FileSystem, worktree_db: WorktreeDb) -> None:
        _init_workspace(fs.base_path)
        service = HistoryShowService(session_id="missing-exec", path=fs.base_path, db=worktree_db.runs)
        result = service.execute()
        assert not result.ok
        assert result.status is HistoryShowStatus.NOT_FOUND
        assert result.run is None
