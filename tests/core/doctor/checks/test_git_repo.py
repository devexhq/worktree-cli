"""Unit tests for worktree.core.doctor.checks.git_repo."""

from pathlib import Path

import pytest

from tests.harness import assert_model_equal
from worktree.core.doctor.checks.git_repo import GitRepoCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext
from worktree.core.git import GitNotFoundError


class GitRepoCheckTests:
    """Unit tests for GitRepoCheck diagnostic outcomes."""

    def test_execute_missing_git_binary_returns_binary_missing_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[tier-1/unit] GitRepoCheck.execute: shutil.which('git') is None -> FAILED with DOCTOR_GIT_BINARY_MISSING."""
        monkeypatch.setattr("worktree.core.doctor.checks.git_repo.shutil.which", lambda _name: None)
        check = GitRepoCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="git.repo",
                name="Git Repository Check",
                category=CheckCategory.GIT,
                status=CheckStatus.FAILED,
                message="git binary was not found on PATH.",
                details={},
                duration_ms=0.0,
                error_code="DOCTOR_GIT_BINARY_MISSING",
                errors=["git binary was not found on PATH."],
                warnings=[],
                fixes=["Install Git and ensure it is available on PATH"],
            ),
        )

    def test_execute_git_disappears_after_which_returns_binary_missing_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[tier-1/unit] GitRepoCheck.execute: shutil.which finds git but GitRunner.run raises GitNotFoundError -> FAILED with DOCTOR_GIT_BINARY_MISSING."""
        monkeypatch.setattr("worktree.core.doctor.checks.git_repo.shutil.which", lambda _name: "/usr/bin/git")

        def _raise_not_found(*_args: object, **_kwargs: object) -> str:
            raise GitNotFoundError("git not found")

        monkeypatch.setattr("worktree.core.doctor.checks.git_repo.GitRunner.run", _raise_not_found)
        check = GitRepoCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="git.repo",
                name="Git Repository Check",
                category=CheckCategory.GIT,
                status=CheckStatus.FAILED,
                message="git binary was not found on PATH.",
                details={},
                duration_ms=0.0,
                error_code="DOCTOR_GIT_BINARY_MISSING",
                errors=["git binary was not found on PATH."],
                warnings=[],
                fixes=["Install Git and ensure it is available on PATH"],
            ),
        )

    def test_execute_outside_git_repository_returns_not_repo_failure(self, tmp_path: Path) -> None:
        """[tier-1/unit] GitRepoCheck.execute: context.cwd has no .git -> FAILED with DOCTOR_GIT_NOT_REPO."""
        check = GitRepoCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="git.repo",
                name="Git Repository Check",
                category=CheckCategory.GIT,
                status=CheckStatus.FAILED,
                message=f"'{tmp_path}' is not a Git repository.",
                details={},
                duration_ms=0.0,
                error_code="DOCTOR_GIT_NOT_REPO",
                errors=[f"'{tmp_path}' is not a Git repository."],
                warnings=[],
                fixes=["Run `git init` to initialize a repository, or run this command from inside an existing one"],
            ),
        )

    def test_execute_inside_git_repository_returns_ok_with_root_and_branch(self, git_repo: Path) -> None:
        """[tier-1/unit] GitRepoCheck.execute: context.cwd=git_repo (main, HEAD resolvable) -> OK with root and branch."""
        check = GitRepoCheck()
        context = DoctorContext(cwd=git_repo)

        result = check.execute(context)

        resolved_root = str(git_repo.resolve())
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="git.repo",
                name="Git Repository Check",
                category=CheckCategory.GIT,
                status=CheckStatus.OK,
                message=f"Git repository detected at '{resolved_root}' on branch 'main'.",
                details={"root": resolved_root, "branch": "main"},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
