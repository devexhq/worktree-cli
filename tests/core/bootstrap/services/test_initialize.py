"""Contract tests for worktree.core.bootstrap.services.initialize.initialize_workspace."""

from __future__ import annotations

import json
from pathlib import Path

from tests.harness.builders import WorkspaceBuilder
from worktree.core.bootstrap.models import BootstrapOutcome, InitFailureMode
from worktree.core.bootstrap.services.initialize import initialize_workspace


class InitializeWorkspaceTests:
    """Contract tests for initialize_workspace preflight and idempotency."""

    def test_initialize_workspace_outside_git_repo_sets_preflight_failure_mode(self, tmp_path: Path) -> None:
        """initialize_workspace: non-git root returns ok=False, failure_mode=PREFLIGHT, bootstrap_result=None, one error naming 'not a valid Git repository'."""
        result = initialize_workspace(tmp_path)

        assert result.ok is False
        assert result.failure_mode == InitFailureMode.PREFLIGHT
        assert result.bootstrap_result is None
        assert len(result.errors) == 1
        assert "not a valid Git repository" in result.errors[0]

    def test_initialize_workspace_outside_git_repo_creates_no_worktree_directory(self, tmp_path: Path) -> None:
        """initialize_workspace: non-git root leaves no '.worktree' directory on disk after the call."""
        initialize_workspace(tmp_path)

        assert not (tmp_path / ".worktree").exists()

    def test_initialize_workspace_idempotent_rerun_preserves_custom_setting(self, tmp_path: Path) -> None:
        """initialize_workspace: rerunning on an initialized git workspace with a custom config.json value returns ok=True, bootstrap_result.outcome=ALREADY_INITIALIZED, and leaves the custom value unchanged."""
        workspace = WorkspaceBuilder(tmp_path / "workspace").with_git().build()
        config_path = workspace / ".worktree" / "config.json"
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["project"]["name"] = "custom-project-name"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        result = initialize_workspace(workspace)

        assert result.ok is True
        assert result.bootstrap_result is not None
        assert result.bootstrap_result.outcome == BootstrapOutcome.ALREADY_INITIALIZED
        persisted = json.loads(config_path.read_text(encoding="utf-8"))
        assert persisted["project"]["name"] == "custom-project-name"
