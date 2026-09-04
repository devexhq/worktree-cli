"""Unit tests for degraded and uninitialized workspace status rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import GitFileSystem, make_cli_context, make_rich_output
from worktree.cli.status.commands.root import status_command
from worktree.cli.ui.formatters.status.common import render_status_summary
from worktree.core.config.loader import ConfigLoadStatus
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
            branch="main",
            is_dirty=False,
            uncommitted_files=0,
        ),
        config=config
        or ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=base / ".worktree" / "config.json",
            is_valid=True,
            config=None,
        ),
        catalog=catalog
        or CatalogStatusInfo(
            exists=False,
            catalog_dir=base / ".worktree" / "catalog",
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        ),
        database=database
        or DatabaseStatusInfo(
            exists=False,
            db_path=base / ".worktree" / "data.db",
            is_accessible=False,
            total_runs=0,
        ),
        sandboxes=sandboxes
        or SandboxStatusInfo(
            active_sandboxes=0,
            total_sandboxes=0,
            max_active_sandboxes=5,
        ),
        warnings=warnings or [],
    )


class TestStatusDegraded:
    """Test suite for degraded and uninitialized status mode rendering."""

    def test_uninitialized_workspace_rendering(self) -> None:
        """Verify uninitialized status table, badges, warnings, and remediation."""
        rich_output, buffer = make_rich_output()
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

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status" in rendered
        assert "Uninitialized" in rendered
        assert "Project Name" in rendered
        assert "CONFIG_NOT_FOUND" in rendered
        assert "Active Git Branch" in rendered
        assert "main" in rendered
        assert "Agent Model" in rendered
        assert "Not Configured" in rendered
        assert "N/A" in rendered
        assert "⚠️ Configuration & Context Warnings:" in rendered
        assert "Worktree workspace is not initialized. Run 'wt init' to configure." in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Run 'wt init' to initialize Worktree in this repository." in rendered

    def test_malformed_json_degraded_rendering(self) -> None:
        """Verify degraded table and syntax repair remediation for malformed config.json."""
        rich_output, buffer = make_rich_output()
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

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "CONFIG_MALFORMED_JSON" in rendered
        assert "⚠️ Configuration & Context Warnings:" in rendered
        assert "Malformed config.json:" in rendered
        assert "Expecting property name enclosed in double quotes" in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Repair JSON syntax in .worktree/config.json or restore from backup." in rendered

    def test_schema_invalid_degraded_rendering(self) -> None:
        """Verify degraded table and schema repair remediation for invalid config schema."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/schema-invalid-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
            errors=["Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- 'version' is a required property"],
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            config=config_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "CONFIG_SCHEMA_INVALID" in rendered
        assert "unknown (invalid config)" in rendered
        assert "Uninitialized" not in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Run 'wt config validate' to inspect schema errors or 'wt init --repair'" in rendered

    def test_schema_invalid_with_raw_project_name_rendering(self) -> None:
        """Verify degraded table renders raw project name from unvalidated config dict."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/schema-invalid-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.SCHEMA_INVALID,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            raw={"version": 1, "project": {"name": "my-broken-app"}},
            config=None,
            errors=["Config schema validation failed (CONFIG_SCHEMA_INVALID):\n- 'concurrency' is a required property"],
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            config=config_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "my-broken-app" in rendered
        assert "CONFIG_SCHEMA_INVALID" in rendered
        assert "Uninitialized" not in rendered

    def test_root_not_object_degraded_rendering(self) -> None:
        """Verify degraded table and object root remediation when config is not a JSON object."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/root-array-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.ROOT_NOT_OBJECT,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
            errors=[f"Malformed config.json at '{root}/.worktree/config.json': root must be an object"],
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            config=config_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "CONFIG_ROOT_NOT_OBJECT" in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Ensure .worktree/config.json contains a JSON object root." in rendered

    def test_path_is_directory_degraded_rendering(self) -> None:
        """Verify degraded table and directory removal remediation when config is a directory."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/dir-config-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.PATH_IS_DIRECTORY,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
            errors=[f"Config path is a directory, not a file: '{root}/.worktree/config.json'"],
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            config=config_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "PATH_IS_DIRECTORY" in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Remove directory at .worktree/config.json and run 'wt init'." in rendered

    def test_unreadable_config_degraded_rendering(self) -> None:
        """Verify degraded table and permission check remediation for unreadable config."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/unreadable-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.UNREADABLE,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
            errors=[f"Unable to read config.json at '{root}/.worktree/config.json': Permission denied"],
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            config=config_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "CONFIG_UNREADABLE" in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Check file permissions for .worktree/config.json." in rendered

    def test_non_git_repository_degraded_rendering(self) -> None:
        """Verify degraded table and git init remediation outside a git repository."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/non-git-dir")
        git_info = GitStatusInfo(
            is_git_repo=False,
            branch="none",
            is_dirty=False,
            uncommitted_files=0,
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=True,
            git=git_info,
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Degraded)" in rendered
        assert "NOT_A_GIT_REPO" in rendered
        assert "Next Steps & Remediation:" in rendered
        assert "Run 'git init' or navigate to a Git repository." in rendered

    def test_combined_non_git_and_missing_config(self) -> None:
        """Verify both remediations are rendered when outside git and missing config."""
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/empty-dir")
        git_info = GitStatusInfo(
            is_git_repo=False,
            branch="none",
            is_dirty=False,
            uncommitted_files=0,
        )
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
        )
        result = _make_status_result(
            root_dir=root,
            is_initialized=False,
            git=git_info,
            config=config_info,
            warnings=["Worktree workspace is not initialized. Run 'wt init' to configure."],
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status" in rendered
        assert "Uninitialized" in rendered
        assert "NOT_A_GIT_REPO" in rendered
        assert "CONFIG_NOT_FOUND" in rendered
        assert "Run 'wt init' to initialize Worktree in this repository." in rendered
        assert "Run 'git init' or navigate to a Git repository." in rendered

    def test_status_command_e2e_uninitialized_returns_ok(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify status_command on an uninitialized workspace returns WorktreeStatusResult."""
        monkeypatch.chdir(git_fs.base_path)
        ctx = make_cli_context(cwd=git_fs.base_path)
        result = status_command(ctx)

        assert not result.is_initialized

        out = capsys.readouterr().out
        assert "Worktree Workspace Status" in out
        assert "Uninitialized" in out
        assert "CONFIG_NOT_FOUND" in out
        assert "Run 'wt init' to initialize Worktree in this repository." in out

    def test_status_command_e2e_corrupted_config_returns_ok(
        self,
        git_fs: GitFileSystem,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify status_command on a corrupted workspace returns WorktreeStatusResult."""
        monkeypatch.chdir(git_fs.base_path)
        config_path = git_fs.base_path / ".worktree" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{bad json: true", encoding="utf-8")

        ctx = make_cli_context(cwd=git_fs.base_path)
        result = status_command(ctx)

        assert not result.ok

        out = capsys.readouterr().out
        assert "Worktree Workspace Status (Degraded)" in out
        assert "CONFIG_MALFORMED_JSON" in out
        assert "Repair JSON syntax in .worktree/config.json or restore from backup." in out
