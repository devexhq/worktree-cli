"""Verification tests for test harness fixtures and assertion helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import typer
from pydantic import BaseModel, Field
from typer.testing import CliRunner

from tests.harness import (
    assert_model_equal,
    assert_result_error,
    assert_result_ok,
)
from worktree.common.constants import REQUIRED_SUBDIRS


class DummyResult(BaseModel):
    """Result model implementing ResultProtocol for assertion tests."""

    success: bool = True
    errors: list[str] = Field(default_factory=list)
    status: str = "ok"

    @property
    def ok(self) -> bool:
        return self.success


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


class AssertResultOkTests:
    """Verification tests for assert_result_ok helper."""

    def test_assert_result_ok_passes_on_successful_result(self) -> None:
        result = DummyResult(success=True, errors=[], status="ok")
        assert_result_ok(result)

    @pytest.mark.parametrize(
        "result",
        [
            pytest.param(DummyResult(success=False, errors=[]), id="ok_is_false"),
            pytest.param(DummyResult(success=True, errors=["some error"]), id="errors_present"),
        ],
    )
    def test_assert_result_ok_fails_on_invalid_result(self, result: DummyResult) -> None:
        with pytest.raises(AssertionError):
            assert_result_ok(result)

    def test_assert_result_ok_matches_expected_status(self) -> None:
        result = DummyResult(success=True, errors=[], status="ready")
        assert_result_ok(result, expected_status="ready")

    def test_assert_result_ok_fails_when_expected_status_mismatches(self) -> None:
        result = DummyResult(success=True, errors=[], status="ready")
        with pytest.raises(AssertionError):
            assert_result_ok(result, expected_status="mismatch")


class AssertResultErrorTests:
    """Verification tests for assert_result_error helper."""

    def test_assert_result_error_passes_on_failed_result(self) -> None:
        result = DummyResult(success=False, errors=["error occurred"])
        assert_result_error(result)

    @pytest.mark.parametrize(
        "result",
        [
            pytest.param(DummyResult(success=True, errors=["error occurred"]), id="ok_is_true"),
            pytest.param(DummyResult(success=False, errors=[]), id="errors_empty"),
        ],
    )
    def test_assert_result_error_fails_on_invalid_result(self, result: DummyResult) -> None:
        with pytest.raises(AssertionError):
            assert_result_error(result)

    def test_assert_result_error_matches_expected_code(self) -> None:
        result = DummyResult(success=False, errors=["NOT_FOUND: missing item"])
        assert_result_error(result, "NOT_FOUND")

    def test_assert_result_error_fails_when_expected_code_absent(self) -> None:
        result = DummyResult(success=False, errors=["NOT_FOUND: missing item"])
        with pytest.raises(AssertionError):
            assert_result_error(result, "MISSING_CODE")

    def test_assert_result_error_matches_expected_status(self) -> None:
        result = DummyResult(success=False, errors=["error occurred"], status="failed")
        assert_result_error(result, expected_status="failed")

    def test_assert_result_error_fails_when_expected_status_mismatches(self) -> None:
        result = DummyResult(success=False, errors=["error occurred"], status="failed")
        with pytest.raises(AssertionError):
            assert_result_error(result, expected_status="mismatch")


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
