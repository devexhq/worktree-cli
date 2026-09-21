"""Tests for worktree.core.status.collector and Status facade."""

from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.harness import StatusBuilder, WorkspaceBuilder
from worktree.common.filesystem import Filesystem
from worktree.core.config.loader import ConfigLoadStatus
from worktree.core.config.models import AgentConfig, ProjectConfig, SandboxConfig, WorktreeConfig
from worktree.core.db import RunsRepository, RunStatus, SandboxesRepository
from worktree.core.git import GitNotFoundError, GitPlumbingTimeoutError, GitRunner
from worktree.core.status import Status, WorktreeStatusResult
from worktree.core.status.services.collector import collect_status


def _config_payload(*, model: str | None = "gpt-4o", max_active_sandboxes: int = 5) -> dict[str, Any]:
    return WorktreeConfig(
        version=1,
        project=ProjectConfig(name="status-ws"),
        agent=AgentConfig(model=model),
        sandbox=SandboxConfig(max_active_sandboxes=max_active_sandboxes),
    ).model_dump(mode="json")


class StatusFacadeTests:
    """Tests for Status domain facade."""

    @pytest.mark.parametrize(
        "invoke",
        [
            pytest.param(lambda workspace: Status(workspace).collect(), id="instance_method"),
            pytest.param(Status.collect_at, id="classmethod"),
        ],
    )
    def test_status_collect_returns_worktree_status_result(
        self,
        tmp_path: Path,
        invoke: Callable[[Path], WorktreeStatusResult],
    ) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "facade_collect")
            .with_git(branch="feature-facade")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        result = invoke(workspace)

        expected = StatusBuilder(workspace).with_git(branch="feature-facade").build()
        assert result == expected


class StatusCollectorGitCollectionTests:
    """Tests for git repository status collection in collect_status."""

    def test_collect_status_clean_worktree(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "clean_ws")
            .with_git(branch="feature-status")
            .with_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        config_data = _config_payload(model="gpt-4o", max_active_sandboxes=3)
        Filesystem.atomic_write_json(fs.config_file, config_data)
        Filesystem.atomic_write_text(fs.catalog_blueprints_dir / "deploy.yml", "name: deploy\n")
        Filesystem.atomic_write_text(fs.catalog_blueprints_dir / "lint-blueprint.yml", "name: lint-blueprint\n")
        Filesystem.atomic_write_text(fs.catalog_steps_dir / "test-step.yml", "name: test-step\n")

        runs_repo = RunsRepository(workspace)
        runs_repo.create(
            session_id="sess-001",
            blueprint_name="deploy",
            blueprint_key="deploy",
            status=RunStatus.COMPLETED,
        )

        sandboxes_repo = SandboxesRepository(workspace)
        sandboxes_repo.create(
            id="sb-001",
            branch_name="wt/sb-001",
            base_commit="HEAD",
            sandbox_path=fs.sandboxes_dir / "sb-001",
        )

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_config(raw=config_data)
            .with_catalog(
                exists=True,
                total_items=3,
                steps_count=1,
                item_names=["deploy", "lint-blueprint", "test-step"],
            )
            .with_database(total_runs=1)
            .with_sandboxes(active_sandboxes=1, total_sandboxes=1, max_active_sandboxes=3)
            .build()
        )
        assert result == expected

    def test_collect_status_dirty_worktree(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "dirty_ws")
            .with_git(branch="feature-dirty")
            .with_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        untracked = workspace / "new_file.txt"
        untracked.write_text("hello", encoding="utf-8")

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_git(branch="feature-dirty", is_dirty=True, uncommitted_files=1)
            .with_warnings("Working tree has 1 uncommitted change(s).")
            .build()
        )
        assert result == expected

    def test_collect_status_detached_head(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "detached_ws")
            .with_git(branch="feature-detached")
            .with_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        commit_hash = GitRunner.run(["rev-parse", "HEAD"], path=workspace).strip()
        subprocess.run(["git", "checkout", commit_hash], cwd=workspace, check=True, capture_output=True)

        result = collect_status(workspace)

        expected = StatusBuilder(workspace).with_git(branch="HEAD (detached)").build()
        assert result == expected

    def test_collect_status_non_git_directory(self, tmp_path: Path) -> None:
        non_git_dir = tmp_path / "non_git"
        non_git_dir.mkdir(parents=True, exist_ok=True)

        result = collect_status(non_git_dir)

        expected = (
            StatusBuilder(non_git_dir)
            .without_git()
            .without_config()
            .without_database()
            .with_warnings("Worktree workspace is not initialized. Run 'wt init' to configure.")
            .with_fixes(
                "Run 'wt init' to initialize Worktree in this repository.",
                "Run 'git init' or navigate to a Git repository.",
            )
            .build()
        )
        assert result == expected

    @pytest.mark.parametrize(
        "git_error",
        [
            pytest.param(GitNotFoundError("git not found"), id="not_found"),
            pytest.param(GitPlumbingTimeoutError("git timed out"), id="timeout"),
        ],
    )
    def test_collect_status_git_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        git_error: Exception,
    ) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "git_error_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        def mock_run(*args: object, **kwargs: object) -> str:
            raise git_error

        monkeypatch.setattr(GitRunner, "run", mock_run)

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_git(is_git_repo=False, branch="unknown")
            .with_fixes("Run 'git init' or navigate to a Git repository.")
            .build()
        )
        assert result == expected

    def test_collect_status_git_rev_parse_not_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "git_false_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        config_data = _config_payload(model="gpt-4o")
        Filesystem.atomic_write_json(fs.config_file, config_data)

        def mock_run(*args: object, **kwargs: object) -> str:
            return "false"

        monkeypatch.setattr(GitRunner, "run", mock_run)

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_git(is_git_repo=False, branch="none")
            .with_fixes("Run 'git init' or navigate to a Git repository.")
            .build()
        )
        assert result == expected


class StatusCollectorConfigAndCatalogTests:
    """Tests for configuration and catalog status collection in collect_status."""

    def test_collect_status_uninitialized_workspace(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "uninit_ws")
            .with_git(branch="feature-uninit")
            .without_config()
            .without_catalog_templates()
            .build()
        )
        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_git(branch="feature-uninit")
            .without_config()
            .with_warnings("Worktree workspace is not initialized. Run 'wt init' to configure.")
            .with_fixes("Run 'wt init' to initialize Worktree in this repository.")
            .build()
        )
        assert result == expected

    def test_collect_status_malformed_config(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "malformed_config_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_text(fs.config_file, "{invalid_json: true")

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_config(
                status=ConfigLoadStatus.MALFORMED_JSON,
                is_valid=False,
                errors=[
                    (
                        f"Malformed config.json at '{fs.config_file}': "
                        "Expecting property name enclosed in double quotes at line 1 column 2 (char 1) (CONFIG_MALFORMED_JSON)."
                    )
                ],
                fixes=["Repair JSON syntax, or restore from backup"],
            )
            .with_warnings(
                "Malformed config.json: Expecting property name enclosed in double quotes at line 1 column 2 (char 1) (CONFIG_MALFORMED_JSON)."
            )
            .with_fixes("Repair JSON syntax in .worktree/config.json or restore from backup.")
            .build()
        )
        assert result == expected

    def test_collect_status_missing_catalog_directory(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "missing_catalog_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        result = collect_status(workspace)

        expected = StatusBuilder(workspace).build()
        assert result == expected

    def test_collect_status_invalid_catalog_blueprint(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "invalid_catalog_bp_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))
        Filesystem.atomic_write_text(fs.catalog_blueprints_dir / "valid-bp.yml", "name: valid-bp\n")
        Filesystem.atomic_write_text(fs.catalog_blueprints_dir / "bad.yml", "invalid: [yaml: broken\n")

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_catalog(
                exists=True,
                total_items=2,
                invalid_items=1,
                item_names=["bad", "valid-bp"],
            )
            .with_warnings("1 invalid blueprint file(s) detected in catalog.")
            .build()
        )
        assert result == expected


class StatusCollectorDatabaseAndSandboxTests:
    """Tests for database and sandbox status collection in collect_status."""

    def test_collect_status_missing_database(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "missing_db_ws")
            .with_git(branch="feature-status")
            .without_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        result = collect_status(workspace)

        expected = StatusBuilder(workspace).without_database().build()
        assert result == expected

    def test_collect_status_corrupted_database(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "corrupted_db_ws")
            .with_git(branch="feature-status")
            .with_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))
        fs.db_file.write_bytes(b"NOT A SQLITE DATABASE")

        result = collect_status(workspace)

        expected = StatusBuilder(workspace).with_database(exists=True, is_accessible=False, total_runs=0).build()
        assert result == expected

    def test_collect_status_sandboxes_directory_fallback(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "sandbox_fallback_ws")
            .with_git(branch="feature-status")
            .without_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        config_payload = _config_payload(model="gpt-4o", max_active_sandboxes=4)
        Filesystem.atomic_write_json(fs.config_file, config_payload)
        (fs.sandboxes_dir / "sb-1").mkdir(parents=True, exist_ok=True)
        (fs.sandboxes_dir / "sb-2").mkdir(parents=True, exist_ok=True)

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_config(raw=config_payload)
            .without_database()
            .with_sandboxes(active_sandboxes=2, total_sandboxes=2, max_active_sandboxes=4)
            .build()
        )
        assert result == expected

    def test_collect_status_sandboxes_db_query_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "sandbox_db_error_ws")
            .with_git(branch="feature-status")
            .with_database()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        runs_repo = RunsRepository(workspace)
        runs_repo.create(
            session_id="sess-test",
            blueprint_name="test-bp",
            blueprint_key="test-bp",
            status=RunStatus.COMPLETED,
        )
        (fs.sandboxes_dir / "sb-fallback").mkdir(parents=True, exist_ok=True)

        def mock_list(*args: object, **kwargs: object) -> list[object]:
            raise RuntimeError("DB query failure")

        monkeypatch.setattr(SandboxesRepository, "list", mock_list)

        result = collect_status(workspace)

        expected = (
            StatusBuilder(workspace)
            .with_database(total_runs=1)
            .with_sandboxes(active_sandboxes=1, total_sandboxes=1)
            .build()
        )
        assert result == expected


class StatusCollectorWarningsOrderingTests:
    """Tests verifying deterministic warning priority order in collect_status."""

    def test_collect_status_warnings_follow_deterministic_priority(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "warnings_order_ws")
            .with_git(branch="main")
            .without_config()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)

        (workspace / "dirty.txt").write_text("dirty content", encoding="utf-8")
        Filesystem.atomic_write_text(fs.catalog_blueprints_dir / "broken.yml", "bad: [yaml\n")

        result = collect_status(workspace)

        assert result.warnings == [
            "Worktree workspace is not initialized. Run 'wt init' to configure.",
            "Active branch is 'main'. Automated workflows on primary branches are discouraged.",
            "Working tree has 1 uncommitted change(s).",
            "1 invalid blueprint file(s) detected in catalog.",
        ]

        Filesystem.atomic_write_json(
            fs.config_file,
            _config_payload(model=None, max_active_sandboxes=8),
        )

        result2 = collect_status(workspace)

        assert result2.warnings == [
            "Active branch is 'main'. Automated workflows on primary branches are discouraged.",
            "Working tree has 1 uncommitted change(s).",
            "Agent model is not configured (agent.model is null).",
            "max_active_sandboxes (8) is unusually high.",
            "1 invalid blueprint file(s) detected in catalog.",
        ]


class StatusCollectorFixesRemediationTests:
    """Tests for actionable remediation fixes in collect_status."""

    def test_collect_status_fixes_for_uninitialized_workspace(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "uninit_fixes_ws")
            .with_git(branch="feature-status")
            .without_config()
            .without_catalog_templates()
            .build()
        )

        result = collect_status(workspace)

        assert result.fixes == ["Run 'wt init' to initialize Worktree in this repository."]

    def test_collect_status_fixes_for_non_git_repo(self, tmp_path: Path) -> None:
        non_git_dir = tmp_path / "non_git_repo"
        fs = Filesystem(non_git_dir)
        Filesystem.atomic_write_json(fs.config_file, _config_payload(model="gpt-4o"))

        result = collect_status(non_git_dir)

        assert result.fixes == ["Run 'git init' or navigate to a Git repository."]

    @pytest.mark.parametrize(
        ("payload", "expected_fix"),
        [
            pytest.param(
                "{bad json: true",
                "Repair JSON syntax in .worktree/config.json or restore from backup.",
                id="malformed_json",
            ),
            pytest.param(
                "{}",
                "Run 'wt config validate' to inspect schema errors or 'wt init --repair' to insert missing keys.",
                id="schema_invalid",
            ),
            pytest.param(
                '["not", "an", "object"]',
                "Ensure .worktree/config.json contains a JSON object root.",
                id="root_not_object",
            ),
        ],
    )
    def test_collect_status_fixes_for_invalid_config_payload(
        self,
        tmp_path: Path,
        payload: str,
        expected_fix: str,
    ) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "invalid_config_fixes_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_text(fs.config_file, payload)

        result = collect_status(workspace)

        assert result.fixes == [expected_fix]

    def test_collect_status_fixes_for_path_is_directory(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "path_is_dir_fixes_ws")
            .with_git(branch="feature-status")
            .without_config()
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        fs.config_file.mkdir(parents=True, exist_ok=True)

        result = collect_status(workspace)

        assert result.fixes == ["Remove directory at .worktree/config.json and run 'wt init'."]

    def test_collect_status_fixes_for_unreadable(self, tmp_path: Path) -> None:
        workspace = (
            WorkspaceBuilder(tmp_path / "unreadable_fixes_ws")
            .with_git(branch="feature-status")
            .without_catalog_templates()
            .build()
        )
        fs = Filesystem(workspace)
        Filesystem.atomic_write_text(fs.config_file, "{}")
        fs.config_file.chmod(0)

        try:
            if os.access(fs.config_file, os.R_OK):
                pytest.skip("filesystem still allows reading unreadable mode")
            result = collect_status(workspace)
            assert result.fixes == ["Check file permissions for .worktree/config.json."]
        finally:
            fs.config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
