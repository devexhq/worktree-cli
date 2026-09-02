"""Unit tests for HistoryListService and HistoryShowService."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FileSystem, make_rich_output, make_run
from worktree.common.utils import RichOutput
from worktree.core.blueprint import BlueprintKind
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

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_collect_all_runs(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-1",
            blueprint_name="task-1",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        make_run(
            self.db.runs,
            session_id="run-2",
            blueprint_name="wf-1",
            kind=BlueprintKind.WORKFLOW,
            status=RunStatus.FAILED,
        )

        service = HistoryListService(path=fs.base_path, db=self.db.runs, output=RichOutput())
        result = service.collect()
        assert result.ok
        assert result.status is HistoryListStatus.OK
        assert len(result.runs) == 2

    def test_collect_filter_by_status(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-ok",
            blueprint_name="task-1",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        make_run(
            self.db.runs,
            session_id="run-fail",
            blueprint_name="task-2",
            kind=BlueprintKind.TASK,
            status=RunStatus.FAILED,
        )

        # Status matching enum
        service = HistoryListService(path=fs.base_path, db=self.db.runs, status="failed", output=RichOutput())
        result = service.collect()
        assert result.ok
        assert len(result.runs) == 1
        assert result.runs[0].session_id == "run-fail"

        # Invalid status string fallback
        service_invalid = HistoryListService(
            path=fs.base_path, db=self.db.runs, status="nonexistent_status", output=RichOutput()
        )
        result_invalid = service_invalid.collect()
        assert result_invalid.ok
        assert len(result_invalid.runs) == 0

    def test_collect_filter_by_kind(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-task",
            blueprint_name="task-1",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        make_run(
            self.db.runs,
            session_id="run-wf",
            blueprint_name="wf-1",
            kind=BlueprintKind.WORKFLOW,
            status=RunStatus.COMPLETED,
        )

        # Kind matching enum
        service = HistoryListService(path=fs.base_path, db=self.db.runs, kind="workflow", output=RichOutput())
        result = service.collect()
        assert result.ok
        assert len(result.runs) == 1
        assert result.runs[0].session_id == "run-wf"

        # Invalid kind string fallback
        service_invalid = HistoryListService(
            path=fs.base_path, db=self.db.runs, kind="invalid_kind", output=RichOutput()
        )
        result_invalid = service_invalid.collect()
        assert result_invalid.ok
        assert len(result_invalid.runs) == 0

    def test_collect_limit(self, fs: FileSystem) -> None:
        for i in range(5):
            make_run(
                self.db.runs,
                session_id=f"run-{i}",
                blueprint_name=f"task-{i}",
                kind=BlueprintKind.TASK,
                status=RunStatus.COMPLETED,
            )

        service = HistoryListService(path=fs.base_path, db=self.db.runs, limit=3, output=RichOutput())
        result = service.collect()
        assert result.ok
        assert len(result.runs) == 3

    def test_execute_renders_output(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-exec",
            blueprint_name="sample-task",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        rich_output, buffer = make_rich_output(width=160)

        service = HistoryListService(path=fs.base_path, db=self.db.runs, output=rich_output)
        result = service.execute()
        assert result.ok
        rich_output.print()
        output = buffer.getvalue()
        assert "Execution History" in output
        assert "run-exec" in output


class HistoryShowServiceTests:
    """Direct unit tests for HistoryShowService data collection and execution."""

    db: WorktreeDb

    @pytest.fixture(autouse=True)
    def setup_method(self, fs: FileSystem) -> None:
        self.db = WorktreeDb(path=fs.base_path)

    def test_collect_found(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-show",
            blueprint_name="show-task",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )

        service = HistoryShowService(session_id="run-show", path=fs.base_path, db=self.db.runs, output=RichOutput())
        result = service.collect()
        assert result.ok
        assert result.status is HistoryShowStatus.OK
        assert result.run is not None
        assert result.run.session_id == "run-show"

    def test_collect_not_found(self, fs: FileSystem) -> None:
        _init_workspace(fs.base_path)
        service = HistoryShowService(
            session_id="missing-session", path=fs.base_path, db=self.db.runs, output=RichOutput()
        )
        result = service.collect()
        assert not result.ok
        assert result.status is HistoryShowStatus.NOT_FOUND
        assert result.run is None

    def test_execute_found_renders_metadata(self, fs: FileSystem) -> None:
        make_run(
            self.db.runs,
            session_id="run-show-exec",
            blueprint_name="show-task",
            kind=BlueprintKind.TASK,
            status=RunStatus.COMPLETED,
        )
        rich_output, buffer = make_rich_output(width=160)

        service = HistoryShowService(session_id="run-show-exec", path=fs.base_path, db=self.db.runs, output=rich_output)
        result = service.execute()
        assert result.ok
        rich_output.print()
        output = buffer.getvalue()
        assert "Session Metadata: run-show-exec" in output
        assert "show-task" in output

    def test_execute_not_found_renders_panel(self, fs: FileSystem) -> None:
        _init_workspace(fs.base_path)
        rich_output, buffer = make_rich_output(width=160)

        service = HistoryShowService(session_id="missing-exec", path=fs.base_path, db=self.db.runs, output=rich_output)
        result = service.execute()
        assert not result.ok
        rich_output.print()
        output = buffer.getvalue()
        assert "Session Not Found" in output
        assert "missing-exec" in output
