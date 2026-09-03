"""Unit tests for worktree.cli.status.renderers."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import make_rich_output
from worktree.cli.ui.formatters.status.common import render_status_summary
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


class TestStatusRenderer:
    """Tests for render_status_summary."""

    def test_render_status_summary_healthy_workspace(self) -> None:
        rich_output, buffer = make_rich_output()
        result = _make_status_result()

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status" in rendered
        assert "Project Name" in rendered
        assert "worktree-cli" in rendered
        assert "Config Status" in rendered
        assert "ok (.worktree/config.json)" in rendered
        assert "Active Git Branch" in rendered
        assert "feature/status-cmd" in rendered
        assert "Agent Model" in rendered
        assert "gemini-2.5-flash" in rendered
        assert "Active Sandboxes" in rendered
        assert "1 / 5 max" in rendered
        assert "Catalog Items" in rendered
        assert "2 valid / 2 total" in rendered
        assert "Configuration & Context Warnings" not in rendered

    def test_render_status_summary_with_warnings(self) -> None:
        rich_output, buffer = make_rich_output()
        result = _make_status_result(
            warnings=[
                "max_active_sandboxes (10) is unusually high.",
                "Active branch is 'main'. Automated workflows on primary branches are discouraged.",
            ]
        )

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status" in rendered
        assert "⚠️ Configuration & Context Warnings:" in rendered
        assert "max_active_sandboxes (10) is unusually high." in rendered
        assert "Active branch is 'main'." in rendered

    def test_render_status_summary_dirty_branch(self) -> None:
        rich_output, buffer = make_rich_output()
        git_info = GitStatusInfo(
            is_git_repo=True,
            branch="feature/dirty-branch",
            is_dirty=True,
            uncommitted_files=3,
        )
        result = _make_status_result(git=git_info)

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "feature/dirty-branch (dirty)" in rendered

    def test_render_status_summary_null_model_and_project(self) -> None:
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/my-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.OK,
            config_path=root / ".worktree" / "config.json",
            is_valid=True,
            config=WorktreeConfig(
                version=1,
                project=ProjectConfig(name=""),
                agent=AgentConfig(model=None),
            ),
        )
        result = _make_status_result(root_dir=root, config=config_info)

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "unnamed_project" in rendered
        assert "Not Configured" in rendered

    def test_render_status_summary_none_config(self) -> None:
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/my-repo")
        config_info = ConfigStatusInfo(
            status=ConfigLoadStatus.NOT_FOUND,
            config_path=root / ".worktree" / "config.json",
            is_valid=False,
            config=None,
        )
        result = _make_status_result(root_dir=root, config=config_info)

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "Worktree Workspace Status (Uninitialized)" in rendered
        assert "Uninitialized" in rendered
        assert "Not Configured" in rendered
        assert "CONFIG_NOT_FOUND" in rendered
        assert "Run 'wt init' to initialize Worktree in this repository." in rendered

    def test_render_status_summary_empty_catalog(self) -> None:
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/my-repo")
        catalog_info = CatalogStatusInfo(
            exists=False,
            catalog_dir=root / ".worktree" / "catalog",
            total_items=0,
            workflows_count=0,
            tasks_count=0,
            steps_count=0,
            invalid_items=0,
            item_names=[],
        )
        result = _make_status_result(root_dir=root, catalog=catalog_info)

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "0 valid / 0 total" in rendered

    def test_render_status_summary_invalid_catalog_items(self) -> None:
        rich_output, buffer = make_rich_output()
        root = Path("/workspace/my-repo")
        catalog_info = CatalogStatusInfo(
            exists=True,
            catalog_dir=root / ".worktree" / "catalog",
            total_items=5,
            workflows_count=2,
            tasks_count=2,
            steps_count=1,
            invalid_items=2,
            item_names=["w1", "w2", "t1", "t2", "s1"],
        )
        result = _make_status_result(root_dir=root, catalog=catalog_info)

        render_status_summary(result, output=rich_output)
        rich_output.print()
        rendered = buffer.getvalue()

        assert "3 valid / 5 total" in rendered
