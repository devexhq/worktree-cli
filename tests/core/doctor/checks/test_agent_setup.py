"""Unit tests for worktree.core.doctor.checks.agent_setup."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness import assert_model_equal
from worktree.core.config.models import AgentConfig, AgentProvider, ProjectConfig, WorktreeConfig
from worktree.core.doctor.checks.agent_setup import PROVIDER_CREDENTIAL_RESOLVERS, AgentSetupCheck
from worktree.core.doctor.models import CheckCategory, CheckStatus, DiagnosticCheckResult, DoctorContext


def _context_with_agent(cwd: Path, agent: AgentConfig) -> DoctorContext:
    config = WorktreeConfig(version=1, project=ProjectConfig(name="demo"), agent=agent)
    return DoctorContext(cwd=cwd, config=config)


class AgentSetupCheckTests:
    """Unit tests for AgentSetupCheck diagnostic outcomes."""

    def test_execute_config_none_defaults_to_local_provider_no_model(self, tmp_path: Path) -> None:
        """[tier-1/unit] AgentSetupCheck.execute: context.config=None -> AgentConfig() default (provider='local', model=None) -> WARNING, error_code='DOCTOR_AGENT_NO_MODEL', details={'provider': 'local'}."""
        check = AgentSetupCheck()
        context = DoctorContext(cwd=tmp_path)

        result = check.execute(context)

        message = "Agent provider 'local' has no model configured."
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="agent.setup",
                name="Agent Setup Check",
                category=CheckCategory.AGENT,
                status=CheckStatus.WARNING,
                message=message,
                details={"provider": "local"},
                duration_ms=0.0,
                error_code="DOCTOR_AGENT_NO_MODEL",
                errors=[],
                warnings=[message],
                fixes=["Configure `agent.model` in `.worktree/config.json`"],
            ),
        )

    def test_execute_local_provider_with_model_returns_ok(self, tmp_path: Path) -> None:
        """[tier-1/unit] AgentSetupCheck.execute: agent.provider='local', agent.model='worktree-local-agent' -> OK, error_code=None, details={'provider': 'local', 'model': 'worktree-local-agent'}."""
        check = AgentSetupCheck()
        context = _context_with_agent(tmp_path, AgentConfig(provider="local", model="worktree-local-agent"))

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="agent.setup",
                name="Agent Setup Check",
                category=CheckCategory.AGENT,
                status=CheckStatus.OK,
                message="Agent provider 'local' is configured with model 'worktree-local-agent'.",
                details={"provider": "local", "model": "worktree-local-agent"},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )

    def test_execute_ollama_provider_no_resolver_missing_model_returns_warning(self, tmp_path: Path) -> None:
        """[tier-1/unit] AgentSetupCheck.execute: agent.provider='ollama', agent.model=None -> WARNING, error_code='DOCTOR_AGENT_NO_MODEL' (never FAILED, ollama has no credential resolver)."""
        check = AgentSetupCheck()
        context = _context_with_agent(tmp_path, AgentConfig(provider="ollama"))

        result = check.execute(context)

        message = "Agent provider 'ollama' has no model configured."
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="agent.setup",
                name="Agent Setup Check",
                category=CheckCategory.AGENT,
                status=CheckStatus.WARNING,
                message=message,
                details={"provider": "ollama"},
                duration_ms=0.0,
                error_code="DOCTOR_AGENT_NO_MODEL",
                errors=[],
                warnings=[message],
                fixes=["Configure `agent.model` in `.worktree/config.json`"],
            ),
        )

    @pytest.mark.parametrize(
        ("provider", "expected_env"),
        [
            pytest.param("cursor", "CURSOR_API_KEY", id="cursor"),
            pytest.param("gemini", "GEMINI_API_KEY", id="gemini"),
            pytest.param("copilot", "GH_TOKEN or GITHUB_TOKEN", id="copilot"),
        ],
    )
    def test_execute_missing_credential_returns_failed_key_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        provider: AgentProvider,
        expected_env: str,
    ) -> None:
        """[tier-1/unit] AgentSetupCheck.execute: provider's resolver entry monkeypatched to return None -> FAILED, error_code='DOCTOR_AGENT_KEY_MISSING', details={'provider': provider, 'missing_env_var': expected_env}."""
        monkeypatch.setitem(PROVIDER_CREDENTIAL_RESOLVERS, provider, (lambda: None, expected_env))
        check = AgentSetupCheck()
        context = _context_with_agent(tmp_path, AgentConfig(provider=provider, model="some-model"))

        result = check.execute(context)

        message = f"Agent provider '{provider}' is missing required credential '{expected_env}'."
        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="agent.setup",
                name="Agent Setup Check",
                category=CheckCategory.AGENT,
                status=CheckStatus.FAILED,
                message=message,
                details={"provider": provider, "missing_env_var": expected_env},
                duration_ms=0.0,
                error_code="DOCTOR_AGENT_KEY_MISSING",
                errors=[message],
                warnings=[],
                fixes=[f"Set the {expected_env} environment variable"],
            ),
        )

    @pytest.mark.parametrize(
        "provider",
        [
            pytest.param("cursor", id="cursor"),
            pytest.param("gemini", id="gemini"),
            pytest.param("copilot", id="copilot"),
        ],
    )
    def test_execute_credential_present_and_model_set_returns_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: AgentProvider
    ) -> None:
        """[tier-1/unit] AgentSetupCheck.execute: provider's resolver entry monkeypatched to return 'fake-key', agent.model='claude-fake' -> OK, error_code=None, details={'provider': provider, 'model': 'claude-fake'}."""
        _, expected_env = PROVIDER_CREDENTIAL_RESOLVERS[provider]
        monkeypatch.setitem(PROVIDER_CREDENTIAL_RESOLVERS, provider, (lambda: "fake-key", expected_env))
        check = AgentSetupCheck()
        context = _context_with_agent(tmp_path, AgentConfig(provider=provider, model="claude-fake"))

        result = check.execute(context)

        assert_model_equal(
            result,
            DiagnosticCheckResult.model_construct(
                check_id="agent.setup",
                name="Agent Setup Check",
                category=CheckCategory.AGENT,
                status=CheckStatus.OK,
                message=f"Agent provider '{provider}' is configured with model 'claude-fake'.",
                details={"provider": provider, "model": "claude-fake"},
                duration_ms=0.0,
                error_code=None,
                errors=[],
                warnings=[],
                fixes=[],
            ),
        )
