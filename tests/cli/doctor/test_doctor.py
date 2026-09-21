"""Single-tier CLI integration tests for wt doctor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.harness.matchers import ANY_DURATION, assert_model_equal
from worktree.cli import app
from worktree.core.doctor import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorReport
from worktree.core.doctor.models import Remediation, RemediationType


def _check_result(
    *,
    check_id: str,
    name: str,
    category: CheckCategory,
    status: CheckStatus,
    message: str,
    details: dict[str, object],
    error_code: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    fixes: list[str] | None = None,
    remediations: list[Remediation] | None = None,
) -> DiagnosticCheckResult:
    """Build a DiagnosticCheckResult with an ANY_DURATION duration_ms, since wall-clock timing is unownable."""
    return DiagnosticCheckResult.model_construct(
        check_id=check_id,
        name=name,
        category=category,
        status=status,
        message=message,
        details=details,
        duration_ms=ANY_DURATION,
        error_code=error_code,
        errors=errors or [],
        warnings=warnings or [],
        fixes=fixes or [],
        remediations=remediations or [],
    )


def _git_repo_ok(workspace: Path) -> DiagnosticCheckResult:
    return _check_result(
        check_id="git.repo",
        name="Git Repository Check",
        category=CheckCategory.GIT,
        status=CheckStatus.OK,
        message=f"Git repository detected at '{workspace}' on branch 'main'.",
        details={"root": str(workspace), "branch": "main"},
    )


def _git_repo_not_a_repository(workspace: Path) -> DiagnosticCheckResult:
    message = f"'{workspace}' is not a Git repository."
    return _check_result(
        check_id="git.repo",
        name="Git Repository Check",
        category=CheckCategory.GIT,
        status=CheckStatus.FAILED,
        message=message,
        details={},
        error_code="DOCTOR_GIT_NOT_REPO",
        errors=[message],
        remediations=[
            Remediation(
                code="DOCTOR_GIT_NOT_REPO",
                title="Initialize Git repository",
                action_type=RemediationType.COMMAND,
                command="git init",
                description="Run `git init` from the workspace root to create the Git repository worktree operations require.",
                doc_path=None,
                is_automated=False,
            )
        ],
    )


def _config_schema_ok() -> DiagnosticCheckResult:
    return _check_result(
        check_id="config.schema",
        name="Config Schema Check",
        category=CheckCategory.CONFIG,
        status=CheckStatus.OK,
        message="`.worktree/config.json` is present and passes schema V1 validation.",
        details={},
    )


def _filesystem_writable_ok(workspace: Path) -> DiagnosticCheckResult:
    worktree_dir = workspace / ".worktree"
    return _check_result(
        check_id="filesystem.writable",
        name="Filesystem Writable Check",
        category=CheckCategory.FILESYSTEM,
        status=CheckStatus.OK,
        message="All configured workspace paths are writable.",
        details={
            "verified_paths": [
                str(worktree_dir),
                str(worktree_dir / "sessions"),
                str(worktree_dir / "artifacts"),
                str(worktree_dir / "sandboxes"),
                str(worktree_dir),
            ]
        },
    )


def _sandbox_refs_ok() -> DiagnosticCheckResult:
    return _check_result(
        check_id="sandbox.refs",
        name="Sandbox References Check",
        category=CheckCategory.SANDBOX,
        status=CheckStatus.OK,
        message="0 sandbox(es) verified against database and Git worktree state.",
        details={"verified_count": 0},
    )


def _env_binaries_ok() -> DiagnosticCheckResult:
    return _check_result(
        check_id="env.binaries",
        name="Environment Binaries Check",
        category=CheckCategory.ENVIRONMENT,
        status=CheckStatus.OK,
        message="1 required binary(s) verified on PATH.",
        details={"verified_binaries": ["git"]},
    )


def _agent_setup_no_model_warning() -> DiagnosticCheckResult:
    message = "Agent provider 'local' has no model configured."
    return _check_result(
        check_id="agent.setup",
        name="Agent Setup Check",
        category=CheckCategory.AGENT,
        status=CheckStatus.WARNING,
        message=message,
        details={"provider": "local"},
        error_code="DOCTOR_AGENT_NO_MODEL",
        warnings=[message],
        remediations=[
            Remediation(
                code="DOCTOR_AGENT_NO_MODEL",
                title="Configure agent model",
                action_type=RemediationType.COMMAND,
                command='wt config set agent.model "<model>"',
                description="Set `agent.model` in `.worktree/config.json` to a model supported by the configured provider, e.g. `wt config set agent.model <model-name>`.",
                doc_path="docs/cli/config.md",
                is_automated=False,
            )
        ],
    )


def _expected_report(workspace: Path, checks: list[DiagnosticCheckResult]) -> DoctorReport:
    """Build the expected DoctorReport for workspace, with an ANY_DURATION total_duration_ms."""
    return DoctorReport.model_construct(
        workspace_root=workspace,
        checks=checks,
        total_duration_ms=ANY_DURATION,
    )


class DoctorCliIntegrationTests:
    """Typer runner integration tests for wt doctor."""

    def test_doctor_cli_healthy_workspace_exits_zero_and_dispatches_report(
        self, cli_runner: CliRunner, doctor_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt doctor: healthy git+config workspace exits 0, dispatches the exact DoctorReport, and renders the checks table."""
        result = cli_runner.invoke(app, ["-p", str(doctor_workspace), "doctor"])

        assert result.exit_code == 0
        assert "Worktree Doctor Report" in result.stdout
        assert "git.repo" in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            _expected_report(
                doctor_workspace,
                [
                    _git_repo_ok(doctor_workspace),
                    _config_schema_ok(),
                    _filesystem_writable_ok(doctor_workspace),
                    _sandbox_refs_ok(),
                    _env_binaries_ok(),
                    _agent_setup_no_model_warning(),
                ],
            ),
        )

    def test_doctor_cli_category_filter_runs_only_matching_check(
        self, cli_runner: CliRunner, doctor_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt doctor --category git: dispatched DoctorReport.checks has exactly the git.repo OK check."""
        result = cli_runner.invoke(app, ["-p", str(doctor_workspace), "doctor", "--category", "git"])

        assert result.exit_code == 0
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            _expected_report(doctor_workspace, [_git_repo_ok(doctor_workspace)]),
        )

    def test_doctor_cli_invalid_category_exits_two_without_dispatch(
        self, cli_runner: CliRunner, doctor_workspace: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt doctor --category bogus: exit code 2 from Typer choice validation; dispatch_spy captures nothing."""
        result = cli_runner.invoke(app, ["-p", str(doctor_workspace), "doctor", "--category", "bogus"])

        assert result.exit_code == 2
        assert dispatch_spy == []

    def test_doctor_cli_non_git_workspace_with_category_git_exits_one(
        self, cli_runner: CliRunner, tmp_path: Path, dispatch_spy: list[Any]
    ) -> None:
        """wt doctor --category git on a non-git directory: exit 1; dispatches the exact FAILED DoctorReport naming the 'git init' fix."""
        result = cli_runner.invoke(app, ["-p", str(tmp_path), "doctor", "--category", "git"])

        assert result.exit_code == 1
        assert "FAILED" in result.stdout
        assert "Initialize Git repository" in result.stdout
        assert "git init" in result.stdout
        assert len(dispatch_spy) == 1
        assert_model_equal(
            dispatch_spy[0],
            _expected_report(tmp_path, [_git_repo_not_a_repository(tmp_path)]),
        )

    def test_doctor_cli_renders_json_wire_payload_for_category_git(
        self, cli_runner: CliRunner, doctor_workspace: Path
    ) -> None:
        """wt doctor --category git --format json: envelope event_type == 'DoctorReport'; payload matches the literal FR-5 shape for the single git.repo check, excluding duration_ms/total_duration_ms which are asserted as non-negative floats."""
        result = cli_runner.invoke(
            app, ["-p", str(doctor_workspace), "doctor", "--category", "git", "--format", "json"]
        )

        assert result.exit_code == 0
        envelope = json.loads(result.stdout)
        assert envelope["event_type"] == "DoctorReport"

        payload = envelope["payload"]
        total_duration_ms = payload.pop("total_duration_ms")
        assert isinstance(total_duration_ms, float)
        assert total_duration_ms >= 0.0

        check_payload = payload["checks"][0]
        check_duration_ms = check_payload.pop("duration_ms")
        assert isinstance(check_duration_ms, float)
        assert check_duration_ms >= 0.0

        assert payload == {
            "ok": True,
            "has_warnings": False,
            "workspace_root": str(doctor_workspace),
            "checks": [
                {
                    "check_id": "git.repo",
                    "name": "Git Repository Check",
                    "category": "git",
                    "status": "ok",
                    "message": f"Git repository detected at '{doctor_workspace}' on branch 'main'.",
                    "details": {"root": str(doctor_workspace), "branch": "main"},
                    "error_code": None,
                    "errors": [],
                    "warnings": [],
                    "remediations": [],
                }
            ],
        }
