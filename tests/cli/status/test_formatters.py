"""Unit tests for WorktreeStatusFormatter and status UI dispatching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Group

from tests.helpers import make_dispatcher_with_buffer, render_rich
from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.cli.ui.formatters.status import (
    WorktreeStatusFormatter,
    register_status_formatters,
)
from worktree.cli.ui.formatters.status.common import clean_error_message
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


@pytest.mark.parametrize(
    ("status", "error_message", "expected_title", "expected_badge", "expected_remediation"),
    [
        pytest.param(
            ConfigLoadStatus.OK,
            None,
            "Worktree Workspace Status",
            "ok (.worktree/config.json)",
            None,
            id="config_ok",
        ),
        pytest.param(
            ConfigLoadStatus.NOT_FOUND,
            None,
            "Worktree Workspace Status (Uninitialized)",
            "CONFIG_NOT_FOUND",
            "Run 'wt init' to initialize Worktree in this repository.",
            id="config_not_found_uninitialized",
        ),
        pytest.param(
            ConfigLoadStatus.MALFORMED_JSON,
            (
                "Malformed config.json at '/workspace/my-repo/.worktree/config.json': "
                "Expecting property name enclosed in double quotes (line 2 col 1) (CONFIG_MALFORMED_JSON).\n"
                "Fix:\n"
                "- repair JSON syntax, or restore from backup"
            ),
            "Worktree Workspace Status (Degraded)",
            "CONFIG_MALFORMED_JSON",
            "Repair JSON syntax in .worktree/config.json or restore from backup.",
            id="config_malformed_json_degraded",
        ),
        pytest.param(
            ConfigLoadStatus.SCHEMA_INVALID,
            "Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- 'version' is a required property",
            "Worktree Workspace Status (Degraded)",
            "CONFIG_SCHEMA_INVALID",
            "Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys.",
            id="config_schema_invalid_degraded",
        ),
        pytest.param(
            ConfigLoadStatus.ROOT_NOT_OBJECT,
            "Malformed config.json at '/workspace/my-repo/.worktree/config.json': root must be an object",
            "Worktree Workspace Status (Degraded)",
            "CONFIG_ROOT_NOT_OBJECT",
            "Ensure .worktree/config.json contains a JSON object root.",
            id="config_root_not_object_degraded",
        ),
        pytest.param(
            ConfigLoadStatus.PATH_IS_DIRECTORY,
            "Config path is a directory, not a file: '/workspace/my-repo/.worktree/config.json'",
            "Worktree Workspace Status (Degraded)",
            "PATH_IS_DIRECTORY",
            "Remove directory at .worktree/config.json and run 'wt init'.",
            id="config_path_is_directory_degraded",
        ),
        pytest.param(
            ConfigLoadStatus.UNREADABLE,
            "Unable to read config.json at '/workspace/my-repo/.worktree/config.json': Permission denied",
            "Worktree Workspace Status (Degraded)",
            "CONFIG_UNREADABLE",
            "Check file permissions for .worktree/config.json.",
            id="config_unreadable_degraded",
        ),
    ],
)
def test_status_formatter_config_modes(
    status: ConfigLoadStatus,
    error_message: str | None,
    expected_title: str,
    expected_badge: str,
    expected_remediation: str | None,
) -> None:
    errors = [error_message] if error_message else []
    is_initialized = status != ConfigLoadStatus.NOT_FOUND
    config_info = ConfigStatusInfo(
        status=status,
        config_path=Path("/workspace/my-repo/.worktree/config.json"),
        is_valid=(status == ConfigLoadStatus.OK),
        config=(
            WorktreeConfig(
                version=1,
                project=ProjectConfig(name="worktree-cli"),
                agent=AgentConfig(model="gemini-2.5-flash"),
            )
            if status == ConfigLoadStatus.OK
            else None
        ),
        errors=errors,
    )
    result = _make_status_result(is_initialized=is_initialized, config=config_info)
    out = render_rich(WorktreeStatusFormatter().to_rich(result))

    assert expected_title in out
    assert expected_badge in out
    if expected_remediation:
        assert expected_remediation in out
    else:
        assert "Next Steps & Remediation:" not in out
    if error_message:
        assert clean_error_message(error_message) in out


@pytest.mark.parametrize(
    ("git_info", "expected_branch_text", "expected_remediation"),
    [
        pytest.param(
            GitStatusInfo(is_git_repo=True, branch="feature/status-cmd", is_dirty=False, uncommitted_files=0),
            "feature/status-cmd",
            None,
            id="clean_git_branch",
        ),
        pytest.param(
            GitStatusInfo(is_git_repo=True, branch="feature/dirty-branch", is_dirty=True, uncommitted_files=3),
            "feature/dirty-branch (dirty)",
            None,
            id="dirty_git_branch",
        ),
        pytest.param(
            GitStatusInfo(is_git_repo=False, branch="none", is_dirty=False, uncommitted_files=0),
            "NOT_A_GIT_REPO",
            "Run 'git init' or navigate to a Git repository.",
            id="not_a_git_repo",
        ),
    ],
)
def test_status_formatter_git_variants(
    git_info: GitStatusInfo,
    expected_branch_text: str,
    expected_remediation: str | None,
) -> None:
    result = _make_status_result(git=git_info)
    out = render_rich(WorktreeStatusFormatter().to_rich(result))

    assert expected_branch_text in out
    if expected_remediation:
        assert expected_remediation in out
        assert "Worktree Workspace Status (Degraded)" in out
    else:
        assert "Worktree Workspace Status" in out


def test_status_formatter_combined_non_git_and_uninitialized() -> None:
    git_info = GitStatusInfo(is_git_repo=False, branch="none", is_dirty=False, uncommitted_files=0)
    config_info = ConfigStatusInfo(
        status=ConfigLoadStatus.NOT_FOUND,
        config_path=Path("/workspace/my-repo/.worktree/config.json"),
        is_valid=False,
        config=None,
    )
    result = _make_status_result(
        is_initialized=False,
        git=git_info,
        config=config_info,
        warnings=["Worktree workspace is not initialized. Run 'wt init' to configure."],
    )
    out = render_rich(WorktreeStatusFormatter().to_rich(result))

    assert "Worktree Workspace Status" in out
    assert "Uninitialized" in out
    assert "NOT_A_GIT_REPO" in out
    assert "CONFIG_NOT_FOUND" in out
    assert "Run 'wt init' to initialize Worktree in this repository." in out
    assert "Run 'git init' or navigate to a Git repository." in out


@pytest.mark.parametrize(
    ("catalog_info", "expected_catalog_text"),
    [
        pytest.param(
            CatalogStatusInfo(
                exists=True,
                catalog_dir=Path("/workspace/my-repo/.worktree/catalog"),
                total_items=2,
                workflows_count=1,
                tasks_count=1,
                steps_count=0,
                invalid_items=0,
                item_names=["deploy", "lint"],
            ),
            "2 valid / 2 total",
            id="valid_catalog_items",
        ),
        pytest.param(
            CatalogStatusInfo(
                exists=False,
                catalog_dir=Path("/workspace/my-repo/.worktree/catalog"),
                total_items=0,
                workflows_count=0,
                tasks_count=0,
                steps_count=0,
                invalid_items=0,
                item_names=[],
            ),
            "0 valid / 0 total",
            id="empty_catalog",
        ),
        pytest.param(
            CatalogStatusInfo(
                exists=True,
                catalog_dir=Path("/workspace/my-repo/.worktree/catalog"),
                total_items=5,
                workflows_count=2,
                tasks_count=2,
                steps_count=1,
                invalid_items=2,
                item_names=["w1", "w2", "t1", "t2", "s1"],
            ),
            "3 valid / 5 total",
            id="catalog_with_invalid_items",
        ),
    ],
)
def test_status_formatter_catalog_variants(
    catalog_info: CatalogStatusInfo,
    expected_catalog_text: str,
) -> None:
    result = _make_status_result(catalog=catalog_info)
    out = render_rich(WorktreeStatusFormatter().to_rich(result))
    assert expected_catalog_text in out


@pytest.mark.parametrize(
    (
        "project_name",
        "raw_config",
        "agent_model",
        "config_status",
        "is_initialized",
        "expected_project",
        "expected_model",
    ),
    [
        pytest.param(
            "worktree-cli",
            None,
            "gemini-2.5-flash",
            ConfigLoadStatus.OK,
            True,
            "worktree-cli",
            "gemini-2.5-flash",
            id="valid_project_with_specified_model",
        ),
        pytest.param(
            "",
            None,
            None,
            ConfigLoadStatus.OK,
            True,
            "unnamed_project",
            "Not Configured",
            id="empty_project_defaults_to_unnamed_and_not_configured",
        ),
        pytest.param(
            None,
            {"version": 1, "project": {"name": "my-broken-app"}},
            None,
            ConfigLoadStatus.SCHEMA_INVALID,
            True,
            "my-broken-app",
            "Not Configured",
            id="schema_invalid_extracts_raw_project_name",
        ),
        pytest.param(
            None,
            None,
            None,
            ConfigLoadStatus.SCHEMA_INVALID,
            True,
            "unknown (invalid config)",
            "Not Configured",
            id="schema_invalid_without_raw_project_shows_unknown_invalid",
        ),
        pytest.param(
            None,
            None,
            None,
            ConfigLoadStatus.NOT_FOUND,
            False,
            "Uninitialized",
            "Not Configured",
            id="uninitialized_shows_uninitialized_project_status",
        ),
    ],
)
def test_status_formatter_project_and_agent_variants(
    project_name: str | None,
    raw_config: dict[str, Any] | None,
    agent_model: str | None,
    config_status: ConfigLoadStatus,
    is_initialized: bool,
    expected_project: str,
    expected_model: str,
) -> None:
    root = Path("/workspace/my-repo")
    config_obj = None
    if config_status == ConfigLoadStatus.OK:
        config_obj = WorktreeConfig(
            version=1,
            project=ProjectConfig(name=project_name or ""),
            agent=AgentConfig(model=agent_model),
        )
    config_info = ConfigStatusInfo(
        status=config_status,
        config_path=root / ".worktree" / "config.json",
        is_valid=(config_status == ConfigLoadStatus.OK),
        raw=raw_config,
        config=config_obj,
    )
    result = _make_status_result(root_dir=root, is_initialized=is_initialized, config=config_info)
    out = render_rich(WorktreeStatusFormatter().to_rich(result))

    assert expected_project in out
    assert expected_model in out


def test_status_formatter_with_warnings() -> None:
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
    assert "max_active_sandboxes (10) is unusually high." in out
    assert "Active branch is 'main'." in out


def test_status_formatter_to_json_serializable() -> None:
    formatter = WorktreeStatusFormatter()
    result = _make_status_result(warnings=["warning-1", "warning-2"])

    dumped = formatter.to_json_serializable(result)
    assert dumped == {
        "root_dir": "/workspace/my-repo",
        "is_initialized": True,
        "git": {
            "is_git_repo": True,
            "branch": "feature/status-cmd",
            "is_dirty": False,
            "uncommitted_files": 0,
        },
        "config": {
            "status": "ok",
            "config_path": "/workspace/my-repo/.worktree/config.json",
            "is_valid": True,
            "raw": None,
            "config": {
                "version": 1,
                "project": {
                    "name": "worktree-cli",
                    "initialized_at": None,
                },
                "paths": {
                    "root_dir": ".worktree",
                    "sessions_dir": ".worktree/sessions",
                    "artifacts_dir": ".worktree/artifacts",
                    "db_path": ".worktree/data.db",
                },
                "sandbox": {
                    "base_ref": "HEAD",
                    "max_active_sandboxes": 3,
                    "default_timeout_seconds": 900,
                },
                "agent": {
                    "provider": "local",
                    "model": "gemini-2.5-flash",
                    "endpoint": None,
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
                "history": {
                    "save_attempt_logs": True,
                    "save_agent_payloads": True,
                    "save_final_diff": True,
                    "max_sessions": 1000,
                },
                "doctor": {
                    "check_git": True,
                    "check_paths_writable": True,
                    "check_config_schema": True,
                    "check_stale_worktrees": True,
                    "check_required_binaries": True,
                },
                "prune": {
                    "remove_stale_worktrees": True,
                    "remove_orphaned_sandboxes": True,
                    "remove_expired_artifacts": False,
                    "artifact_ttl_days": 30,
                },
                "telemetry": {
                    "enabled": False,
                },
                "concurrency": {
                    "lock_timeout_seconds": 30.0,
                },
            },
            "errors": [],
            "fixes": [],
        },
        "catalog": {
            "exists": True,
            "catalog_dir": "/workspace/my-repo/.worktree/catalog",
            "total_items": 2,
            "workflows_count": 1,
            "tasks_count": 1,
            "steps_count": 0,
            "invalid_items": 0,
            "item_names": ["deploy", "lint"],
        },
        "database": {
            "exists": True,
            "db_path": "/workspace/my-repo/.worktree/data.db",
            "is_accessible": True,
            "total_runs": 1,
        },
        "sandboxes": {
            "active_sandboxes": 1,
            "total_sandboxes": 1,
            "max_active_sandboxes": 5,
        },
        "warnings": ["warning-1", "warning-2"],
        "errors": [],
        "fixes": [],
    }


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


def test_dispatcher_terminal_format() -> None:
    dispatcher, buf = make_dispatcher_with_buffer(force_terminal=True)
    register_status_formatters(dispatcher)
    result = _make_status_result()

    dispatcher.dispatch(result, output_format="terminal")

    output = buf.getvalue()
    assert "Worktree Workspace Status" in output
    assert "worktree-cli" in output
