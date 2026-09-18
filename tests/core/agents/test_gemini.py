"""Tests for the Gemini CLI direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.harness import (
    ANY_ENV,
    ANY_STRING,
    AgentRequestBuilder,
    AgentResponseBuilder,
    FakeAgentRunner,
    FakeAgentRunnerCall,
    assert_model_equal,
)
from worktree.core.agents import AgentResponseStatus
from worktree.core.agents.cli_mutation import CliMutationOutcome, CliMutationRunRequest
from worktree.core.agents.gemini import (
    GEMINI_API_KEY_ENV,
    GeminiAgentAdapter,
    default_gemini_run,
    resolve_gemini_api_key,
)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GEMINI_API_KEY_ENV, "test-key")


class GeminiAuthTests:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            pytest.param({GEMINI_API_KEY_ENV: "abc"}, "abc", id="key_present"),
            pytest.param({}, None, id="unset"),
        ],
    )
    def test_resolve_checks_gemini_api_key(self, env: dict[str, str], expected: str | None) -> None:
        """GEMINI_API_KEY resolves when present; an empty environment resolves to None."""
        assert resolve_gemini_api_key(env) == expected

    def test_preflight_requires_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing GEMINI_API_KEY fails preflight before any run."""
        monkeypatch.delenv(GEMINI_API_KEY_ENV, raising=False)
        adapter = GeminiAgentAdapter()

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(tmp_path).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_errors(
                "Agent provider error (AGENT_PROVIDER_ERROR): missing GEMINI_API_KEY. Fix: export GEMINI_API_KEY=..."
            )
            .build(),
        )


class GeminiRunTests:
    def test_default_run_parses_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """gemini is invoked with the fixed argv plus the requested model, and its JSON stdout is parsed to text."""
        runner = FakeAgentRunner().returning(stdout=b'{"response": "pong"}')
        monkeypatch.setattr("worktree.core.agents.gemini.run_isolated_process", runner)

        outcome = default_gemini_run(
            CliMutationRunRequest(
                sandbox_path=tmp_path,
                prompt="hi",
                model="gemini-2.5-flash",
                timeout_seconds=3,
            )
        )

        assert_model_equal(outcome, CliMutationOutcome(status="finished", result_text="pong", error_detail=None))
        # env is ANY_ENV, not a pinned literal, because it's os.environ.copy() plus the
        # resolved API key and so is host-dependent; the follow-up assertion pins the one
        # key this test does own.
        assert_model_equal(
            runner.last_call,
            FakeAgentRunnerCall.model_construct(
                cmd=["gemini", "-p", "", "-o", "json", "--yolo", "-m", "gemini-2.5-flash"],
                cwd=tmp_path,
                env=ANY_ENV,
                input_data=b"hi",
                timeout_seconds=3,
            ),
        )
        assert runner.last_call.env[GEMINI_API_KEY_ENV] == "test-key"

    def test_missing_gemini_binary_returns_error_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing gemini binary maps to an error outcome naming the Gemini CLI."""
        runner = FakeAgentRunner().raising(FileNotFoundError("gemini"))
        monkeypatch.setattr("worktree.core.agents.gemini.run_isolated_process", runner)

        outcome = default_gemini_run(
            CliMutationRunRequest(sandbox_path=tmp_path, prompt="hi", model=None, timeout_seconds=3)
        )

        # error_detail is ANY_STRING here, not a pinned literal, because it embeds a live
        # external URL (the gemini-cli repo link) not worth hard-pinning; the follow-up
        # assertion below pins the "install the Gemini CLI" part this test does own.
        assert_model_equal(
            outcome,
            CliMutationOutcome.model_construct(status="error", result_text=None, error_detail=ANY_STRING),
        )
        assert outcome.error_detail is not None and "install the Gemini CLI" in outcome.error_detail

    def test_process_timeout_returns_timeout_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A subprocess timeout maps to a timeout outcome."""
        runner = FakeAgentRunner().raising(subprocess.TimeoutExpired(cmd="gemini", timeout=3))
        monkeypatch.setattr("worktree.core.agents.gemini.run_isolated_process", runner)

        outcome = default_gemini_run(
            CliMutationRunRequest(sandbox_path=tmp_path, prompt="hi", model=None, timeout_seconds=3)
        )

        assert_model_equal(outcome, CliMutationOutcome(status="timeout", result_text=None, error_detail=None))
