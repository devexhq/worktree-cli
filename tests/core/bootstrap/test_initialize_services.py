"""Tests for `worktree.core.bootstrap.services.initialize`."""

from __future__ import annotations

import json

import pytest

from tests.helpers import FileSystem, GitFileSystem
from worktree.core.bootstrap import InitFailureMode
from worktree.core.bootstrap.services import initialize as initialize_module
from worktree.core.bootstrap.services.initialize import initialize_workspace
from worktree.core.config.generator import ConfigGenerationResult


class InitializeWorkspaceTests:
    """Tests for `initialize_workspace` service."""

    def test_initialize_workspace_success(self, git_fs: GitFileSystem) -> None:
        result = initialize_workspace(git_fs.base_path, tool_version="0.1.1")

        assert result.ok
        assert result.bootstrap_result is not None
        assert result.bootstrap_result.root_created
        assert result.config_result is not None
        assert result.config_result.created
        assert result.seed_result is not None
        assert not result.errors

        root = git_fs.base_path / ".worktree"
        assert (root / "config.json").is_file()
        assert (root / "data.db").is_file()
        assert (root / "catalog" / "workflows" / "wt" / "fix-tests.yml").is_file()

    def test_initialize_workspace_not_git_repo(self, fs: FileSystem) -> None:
        result = initialize_workspace(fs.base_path, tool_version="0.1.1")

        assert not result.ok
        assert any("not a valid Git repository" in err for err in result.errors)
        assert result.bootstrap_result is None

    def test_initialize_workspace_repair(self, git_fs: GitFileSystem) -> None:
        # Initial run
        initialize_workspace(git_fs.base_path, tool_version="0.1.1")

        # Corrupt/delete a required key from config
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        del data["telemetry"]
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        # Run with repair
        result = initialize_workspace(git_fs.base_path, tool_version="0.1.1", repair=True)
        assert result.ok
        assert result.config_result is not None
        assert result.config_result.repaired
        assert "telemetry" in result.config_result.inserted_keys

    def test_initialize_workspace_overwrite(self, git_fs: GitFileSystem) -> None:
        # Initial run
        initialize_workspace(git_fs.base_path, tool_version="0.1.1")

        # Modify config
        config_path = git_fs.base_path / ".worktree" / "config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["project"]["name"] = "stale-name"
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        # Run with overwrite
        result = initialize_workspace(git_fs.base_path, tool_version="0.1.1", overwrite=True)
        assert result.ok
        assert result.config_result is not None
        assert result.config_result.overwritten
        reloaded = json.loads(config_path.read_text(encoding="utf-8"))
        assert reloaded["project"]["name"] == git_fs.base_path.name

    def test_initialize_workspace_preflight_sets_failure_mode(self, fs: FileSystem) -> None:
        result = initialize_workspace(fs.base_path)
        assert result.failure_mode == InitFailureMode.PREFLIGHT

    def test_initialize_workspace_bootstrap_failure_sets_failure_mode(self, git_fs: GitFileSystem) -> None:
        (git_fs.base_path / ".worktree").write_text("not a dir", encoding="utf-8")
        result = initialize_workspace(git_fs.base_path)
        assert result.failure_mode == InitFailureMode.BOOTSTRAP

    def test_initialize_workspace_config_failure_sets_failure_mode(
        self, git_fs: GitFileSystem, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            initialize_module,
            "generate_default_config",
            lambda *args, **kwargs: ConfigGenerationResult(errors=["Config generation failed"]),
        )
        result = initialize_workspace(git_fs.base_path)
        assert result.failure_mode == InitFailureMode.CONFIG_GENERATION

    def test_initialize_workspace_success_sets_none_failure_mode(self, git_fs: GitFileSystem) -> None:
        result = initialize_workspace(git_fs.base_path)
        assert result.failure_mode is None
