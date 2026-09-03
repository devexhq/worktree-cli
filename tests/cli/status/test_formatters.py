"""Unit tests for WorktreeStatusFormatter and status UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console, Group
from rich.table import Table

from tests.helpers import render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.status import (
    WorktreeStatusFormatter,
    register_status_formatters,
)
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import AgentConfig, ProjectConfig, WorktreeConfig
from worktree.core.status.models import (
    CatalogStatusInfo,
    ConfigStatusInfo,
    DatabaseStatusInfo,
    GitStatusInfo,
    SandboxStatusInfo,
    WorktreeStatusResult,
)


def _make_status_result(
    *,
    root_dir: Path | None = None,
    is_initialized: bool = True,
    git: GitStatusInfo | None = None,
    config: ConfigStatusInfo | None = None,
    catalog: CatalogStatusInfo | None = None,
    database: DatabaseStatusInfo | None = None,
    sandboxes: SandboxStatusInfo | None = None,
    warnings: list[str] | None = None,
) -> WorktreeStatusResult:
    base = root_dir or Path("/workspace/my-repo")
    return WorktreeStatusResult(
        root_dir=base,
        is_initialized=is_initialized,
        git=git
        or GitStatusInfo(
            is_git_repo=True,
            branch="feature/status-cmd",
            is_dirty=False,
            uncommitted_files=0,
        ),
        config=config
        or ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=base / ".worktree" / "config.json",
            is_valid=True,
            config=WorktreeConfig(
                version=1,
                project=ProjectConfig(name="worktree-cli"),
                agent=AgentConfig(model="gemini-2.5-flash"),
            ),
        ),
        catalog=catalog
        or CatalogStatusInfo(
            exists=True,
            catalog_dir=base / ".worktree" / "catalog",
            total_items=2,
            workflows_count=1,
            tasks_count=1,
            steps_count=0,
            invalid_items=0,
            item_names=["deploy", "lint"],
        ),
        database=database
        or DatabaseStatusInfo(
            exists=True,
            db_path=base / ".worktree" / "data.db",
            is_accessible=True,
            total_runs=1,
        ),
        sandboxes=sandboxes
        or SandboxStatusInfo(
            active_sandboxes=1,
            total_sandboxes=1,
            max_active_sandboxes=5,
        ),
        warnings=warnings or [],
    )


def test_worktree_status_formatter_to_rich_healthy() -> None:
    formatter = WorktreeStatusFormatter()
    result = _make_status_result()

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Table)

    out = render_rich(rich_renderable)
    assert "Worktree Workspace Status" in out
    assert "Project Name" in out
    assert "worktree-cli" in out
    assert "Config Status" in out
    assert "ok (.worktree/config.json)" in out
    assert "Active Git Branch" in out
    assert "feature/status-cmd" in out
    assert "Agent Model" in out
    assert "gemini-2.5-flash" in out
    assert "Active Sandboxes" in out
    assert "1 / 5 max" in out
    assert "Catalog Items" in out
    assert "2 valid / 2 total" in out
    assert "Configuration & Context Warnings" not in out


def test_worktree_status_formatter_to_rich_with_warnings() -> None:
    formatter = WorktreeStatusFormatter()
    result = _make_status_result(
        warnings=[
            "max_active_sandboxes (10) is unusually high.",
            "Active branch is 'main'. Automated workflows on primary branches are discouraged.",
        ]
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    out = render_rich(rich_renderable)
    assert "Worktree Workspace Status" in out
    assert "⚠️ Configuration & Context Warnings:" in out
    assert "max_active_sandboxes (10) is unusually high." in out
    assert "Active branch is 'main'." in out


def test_worktree_status_formatter_to_rich_uninitialized() -> None:
    formatter = WorktreeStatusFormatter()
    root = Path("/workspace/uninit-repo")
    config_info = ConfigStatusInfo(
        status=ConfigLoadStatus.NOT_FOUND,
        config_path=root / ".worktree" / "config.json",
        is_valid=False,
        config=None,
    )
    result = _make_status_result(
        root_dir=root,
        is_initialized=False,
        config=config_info,
        warnings=["Worktree workspace is not initialized. Run 'wt init' to configure."],
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    out = render_rich(rich_renderable)
    assert "Worktree Workspace Status (Uninitialized)" in out
    assert "Uninitialized" in out
    assert "CONFIG_NOT_FOUND" in out
    assert "Worktree workspace is not initialized. Run 'wt init' to configure." in out
    assert "Next Steps & Remediation:" in out
    assert "Run 'wt init' to initialize Worktree in this repository." in out


def test_worktree_status_formatter_to_rich_degraded() -> None:
    formatter = WorktreeStatusFormatter()
    root = Path("/workspace/malformed-repo")
    config_info = ConfigStatusInfo(
        status=ConfigLoadStatus.MALFORMED_JSON,
        config_path=root / ".worktree" / "config.json",
        is_valid=False,
        config=None,
        errors=[
            f"Malformed config.json at '{root}/.worktree/config.json': "
            "Expecting property name enclosed in double quotes (line 2 col 1) (CONFIG_MALFORMED_JSON).\n"
            "Fix:\n"
            "- repair JSON syntax, or restore from backup"
        ],
    )
    result = _make_status_result(
        root_dir=root,
        is_initialized=True,
        config=config_info,
    )

    rich_renderable = formatter.to_rich(result)
    assert isinstance(rich_renderable, Group)

    out = render_rich(rich_renderable)
    assert "Worktree Workspace Status (Degraded)" in out
    assert "CONFIG_MALFORMED_JSON" in out
    assert "⚠️ Configuration & Context Warnings:" in out
    assert "Malformed config.json: Expecting property name enclosed in double quotes (line 2 col 1)" in out
    assert "Next Steps & Remediation:" in out
    assert "Repair JSON syntax in .worktree/config.json or restore from backup." in out


def test_worktree_status_formatter_to_rich_dirty_branch() -> None:
    formatter = WorktreeStatusFormatter()
    git_info = GitStatusInfo(
        is_git_repo=True,
        branch="feature/dirty-branch",
        is_dirty=True,
        uncommitted_files=3,
    )
    result = _make_status_result(git=git_info)

    rich_renderable = formatter.to_rich(result)
    out = render_rich(rich_renderable)

    assert "feature/dirty-branch (dirty)" in out


def test_worktree_status_formatter_to_json_serializable() -> None:
    formatter = WorktreeStatusFormatter()
    result = _make_status_result(warnings=["warning-1", "warning-2"])

    dumped = formatter.to_json_serializable(result)
    assert isinstance(dumped, dict)
    assert dumped["root_dir"] == "/workspace/my-repo"
    assert dumped["is_initialized"] is True
    assert dumped["git"]["branch"] == "feature/status-cmd"
    assert dumped["git"]["is_dirty"] is False
    assert dumped["config"]["status"] == "ok"
    assert dumped["config"]["is_valid"] is True
    assert dumped["config"]["config"]["project"]["name"] == "worktree-cli"
    assert dumped["config"]["config"]["agent"]["model"] == "gemini-2.5-flash"
    assert dumped["catalog"]["total_items"] == 2
    assert dumped["database"]["total_runs"] == 1
    assert dumped["sandboxes"]["active_sandboxes"] == 1
    assert dumped["sandboxes"]["max_active_sandboxes"] == 5
    assert dumped["warnings"] == ["warning-1", "warning-2"]

    # Verify JSON encoding works with no error
    encoded = json.dumps(dumped)
    decoded = json.loads(encoded)
    assert decoded["root_dir"] == "/workspace/my-repo"


def test_register_status_formatters_custom_dispatcher() -> None:
    dispatcher = UiDispatcher()
    register_status_formatters(dispatcher)

    assert WorktreeStatusResult in dispatcher._registry
    assert isinstance(dispatcher._registry[WorktreeStatusResult], WorktreeStatusFormatter)


def test_ui_dispatcher_registration() -> None:
    assert WorktreeStatusResult in ui_dispatcher._registry
    assert isinstance(ui_dispatcher._registry[WorktreeStatusResult], WorktreeStatusFormatter)


def test_dispatcher_json_format_ndjson(capsys: pytest.CaptureFixture[str]) -> None:
    dispatcher = UiDispatcher()
    register_status_formatters(dispatcher)
    result = _make_status_result()

    dispatcher.dispatch(result, output_format="json")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event_type"] == "WorktreeStatusResult"
    assert payload["payload"]["root_dir"] == "/workspace/my-repo"
    assert payload["payload"]["config"]["status"] == "ok"


def test_dispatcher_terminal_format(capsys: pytest.CaptureFixture[str]) -> None:
    console = Console(force_terminal=True, width=120)
    dispatcher = UiDispatcher(console=console)
    register_status_formatters(dispatcher)
    result = _make_status_result()

    dispatcher.dispatch(result, output_format="terminal")

    captured = capsys.readouterr()
    assert "Worktree Workspace Status" in captured.out
    assert "worktree-cli" in captured.out
