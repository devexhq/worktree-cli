"""Unit tests for worktree.core.doctor.checks.env_binaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness import assert_model_equal
from worktree.core.config.models import AgentConfig, AgentProvider, ProjectConfig, WorktreeConfig
from worktree.core.doctor.checks.env_binaries import EnvBinariesCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext


def _context_with_provider(cwd: Path, provider: AgentProvider) -> DoctorContext:
    config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"), agent=AgentConfig(provider=provider))
    return DoctorContext(cwd=cwd, config=config)


class EnvBinariesCheckTests:
    """Unit tests for EnvBinariesCheck diagnostic outcomes."""

    def test_execute_missing_git_binary_returns_warning(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """[tier-1/unit] EnvBinariesCheck.execute: shutil.which('git') is None, config=None -> WARNING, error_code='DOCTOR_BINARY_MISSING', details={'missing_binaries': ['git']}."""
        monkeypatch.setattr("worktree.core.doctor.checks.env_binaries.shutil.which", lambda _name: None)
        check = EnvBinariesCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        message = "1 required binary(s) not found on PATH: git."
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="env.binaries",
                name="Environment Binaries Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.WARNING,
                message=message,
                details={"missing_binaries": ["git"]},
                duration_ms=0.0,
                error_code="DOCTOR_BINARY_MISSING",
                errors=[],
                warnings=[message],
                fixes=["Install 'git' and ensure it is available on PATH"],
            ),
        )

    def test_execute_config_none_defaults_to_local_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[tier-1/unit] EnvBinariesCheck.execute: context.config=None, git present on PATH -> OK, details={'verified_binaries': ['git']}, error_code=None."""
        monkeypatch.setattr("worktree.core.doctor.checks.env_binaries.shutil.which", lambda _name: "/usr/bin/git")
        check = EnvBinariesCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="env.binaries",
                name="Environment Binaries Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.OK,
                message="1 required binary(s) verified on PATH.",
                details={"verified_binaries": ["git"]},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        "provider",
        [pytest.param("local", id="local"), pytest.param("ollama", id="ollama"), pytest.param("cursor", id="cursor")],
    )
    def test_execute_provider_without_required_binary_returns_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: AgentProvider
    ) -> None:
        """[tier-1/unit] EnvBinariesCheck.execute: agent.provider has no PROVIDER_REQUIRED_BINARY entry, git present -> OK, details={'verified_binaries': ['git']}."""
        monkeypatch.setattr("worktree.core.doctor.checks.env_binaries.shutil.which", lambda _name: "/usr/bin/git")
        check = EnvBinariesCheck()
        context = _context_with_provider(tmp_path, provider)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="env.binaries",
                name="Environment Binaries Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.OK,
                message="1 required binary(s) verified on PATH.",
                details={"verified_binaries": ["git"]},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    @pytest.mark.parametrize(
        ("provider", "provider_binary"),
        [pytest.param("gemini", "gemini", id="gemini"), pytest.param("copilot", "gh", id="copilot")],
    )
    def test_execute_provider_binary_missing_returns_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: AgentProvider, provider_binary: str
    ) -> None:
        """[tier-1/unit] EnvBinariesCheck.execute: git present, provider CLI binary absent -> WARNING, error_code='DOCTOR_BINARY_MISSING', details={'missing_binaries': [provider_binary]}."""

        def _which(name: str) -> str | None:
            return "/usr/bin/git" if name == "git" else None

        monkeypatch.setattr("worktree.core.doctor.checks.env_binaries.shutil.which", _which)
        check = EnvBinariesCheck()
        context = _context_with_provider(tmp_path, provider)

        result = check.execute(context)

        message = f"1 required binary(s) not found on PATH: {provider_binary}."
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="env.binaries",
                name="Environment Binaries Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.WARNING,
                message=message,
                details={"missing_binaries": [provider_binary]},
                duration_ms=0.0,
                error_code="DOCTOR_BINARY_MISSING",
                errors=[],
                warnings=[message],
                fixes=[f"Install '{provider_binary}' and ensure it is available on PATH"],
            ),
        )

    @pytest.mark.parametrize(
        ("provider", "provider_binary"),
        [pytest.param("gemini", "gemini", id="gemini"), pytest.param("copilot", "gh", id="copilot")],
    )
    def test_execute_provider_binary_present_returns_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: AgentProvider, provider_binary: str
    ) -> None:
        """[tier-1/unit] EnvBinariesCheck.execute: git and provider CLI binary both present -> OK, details={'verified_binaries': ['git', provider_binary]}."""
        monkeypatch.setattr("worktree.core.doctor.checks.env_binaries.shutil.which", lambda _name: "/usr/bin/tool")
        check = EnvBinariesCheck()
        context = _context_with_provider(tmp_path, provider)

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="env.binaries",
                name="Environment Binaries Check",
                category=CheckCategory.ENVIRONMENT,
                status=CheckStatus.OK,
                message="2 required binary(s) verified on PATH.",
                details={"verified_binaries": ["git", provider_binary]},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
