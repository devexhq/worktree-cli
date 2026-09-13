"""Verification tests for test harness fixtures and assertion helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import typer
from pydantic import BaseModel
from typer.testing import CliRunner

from tests.harness import assert_model_equal
from worktree.common.constants import REQUIRED_SUBDIRS


class DummyModel(BaseModel):
    """Pydantic model for model equality assertion tests."""

    name: str
    count: int
    timestamp: str = "2026-01-01T00:00:00Z"


class IsolatedWorkspaceFixtureTests:
    """Verification tests for isolated_workspace fixture."""

    def test_isolated_workspace_creates_worktree_structure(self, isolated_workspace: Path) -> None:
        dot_worktree = isolated_workspace / ".worktree"
        assert dot_worktree.is_dir()
        for subdir in REQUIRED_SUBDIRS:
            assert (dot_worktree / subdir).is_dir()
        assert (dot_worktree / "sandboxes").is_dir()
        assert (dot_worktree / "catalog").is_dir()


class GitRepoFixtureTests:
    """Verification tests for git_repo fixture."""

    def test_git_repo_initializes_valid_git_repository_on_main(self, git_repo: Path) -> None:
        assert (git_repo / ".git").is_dir()

        branch_proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert branch_proc.stdout.strip() == "main"

        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        head_sha = head_proc.stdout.strip()
        assert len(head_sha) == 40

    @pytest.mark.parametrize(
        ("config_key", "expected_value"),
        [
            pytest.param("user.name", "Test User", id="name"),
            pytest.param("user.email", "test@example.com", id="email"),
        ],
    )
    def test_git_repo_configures_local_user_identity(
        self,
        git_repo: Path,
        config_key: str,
        expected_value: str,
    ) -> None:
        proc = subprocess.run(
            ["git", "config", config_key],
            cwd=git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert proc.stdout.strip() == expected_value


class CliRunnerFixtureTests:
    """Verification tests for cli_runner fixture."""

    def test_cli_runner_sets_columns_and_no_color(self, cli_runner: CliRunner) -> None:
        app = typer.Typer()

        @app.command()
        def check_env() -> None:
            assert os.environ.get("COLUMNS") == "160"
            assert os.environ.get("NO_COLOR") == "1"

        result = cli_runner.invoke(app)
        assert result.exit_code == 0


class AssertModelEqualTests:
    """Verification tests for assert_model_equal helper."""

    @pytest.mark.parametrize(
        "expected",
        [
            pytest.param(DummyModel(name="item", count=42), id="model"),
            pytest.param(
                {"name": "item", "count": 42, "timestamp": "2026-01-01T00:00:00Z"},
                id="dict",
            ),
        ],
    )
    def test_assert_model_equal_passes_on_identical_targets(
        self,
        expected: DummyModel | dict[str, object],
    ) -> None:
        model = DummyModel(name="item", count=42)
        assert_model_equal(model, expected)

    @pytest.mark.parametrize(
        "expected",
        [
            pytest.param(DummyModel(name="item", count=42, timestamp="different"), id="model"),
            pytest.param(
                {"name": "item", "count": 42, "timestamp": "different"},
                id="dict",
            ),
        ],
    )
    def test_assert_model_equal_applies_exclusions(
        self,
        expected: DummyModel | dict[str, object],
    ) -> None:
        model = DummyModel(name="item", count=42, timestamp="2026-01-01T00:00:00Z")
        assert_model_equal(model, expected, exclude={"timestamp"})

    @pytest.mark.parametrize(
        "expected",
        [
            pytest.param(DummyModel(name="item", count=99), id="model"),
            pytest.param(
                {"name": "item", "count": 99, "timestamp": "2026-01-01T00:00:00Z"},
                id="dict",
            ),
        ],
    )
    def test_assert_model_equal_fails_on_unexcluded_difference(
        self,
        expected: DummyModel | dict[str, object],
    ) -> None:
        model = DummyModel(name="item", count=42)
        with pytest.raises(AssertionError):
            assert_model_equal(model, expected)
