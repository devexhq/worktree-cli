"""Tests for the GitHub Copilot CLI direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.harness import AgentRequestBuilder, AgentResponseBuilder, assert_model_equal
from worktree.core.agents import AgentResponseStatus
from worktree.core.agents.cli_mutation import CliMutationOutcome, CliMutationRunRequest
from worktree.core.agents.copilot import (
    CopilotAgentAdapter,
    default_copilot_run,
    resolve_copilot_token,
)


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")


class CopilotAuthTests:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            pytest.param({"GH_TOKEN": "abc"}, "abc", id="gh_token"),
            pytest.param({"GITHUB_TOKEN": "xyz"}, "xyz", id="github_token_fallback"),
            pytest.param({}, None, id="unset"),
        ],
    )
    def test_resolve_checks_gh_token_before_github_token(self, env: dict[str, str], expected: str | None) -> None:
        """GH_TOKEN takes priority over GITHUB_TOKEN; an empty environment resolves to None."""
        assert resolve_copilot_token(env) == expected

    def test_preflight_requires_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing both GH_TOKEN and GITHUB_TOKEN fails preflight before any run."""
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        adapter = CopilotAgentAdapter()

        resp = adapter.propose_fix(AgentRequestBuilder().with_sandbox_path(tmp_path).build())

        assert_model_equal(
            resp,
            AgentResponseBuilder()
            .with_status(AgentResponseStatus.PROVIDER_ERROR)
            .with_errors(
                "Agent provider error (AGENT_PROVIDER_ERROR): "
                "missing GH_TOKEN or GITHUB_TOKEN. Fix: export GH_TOKEN=..."
            )
            .build(),
        )


class CopilotRunTests:
    def test_default_run_parses_jsonl(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """gh copilot is invoked with the fixed argv and its JSONL stream is parsed to text."""
        captured: dict[str, Any] = {}

        def fake_run(
            cmd: list[str],
            *,
            cwd: Path,
            env: dict[str, str],
            input_data: bytes,
            timeout_seconds: float,
            **kwargs: object,
        ) -> subprocess.CompletedProcess[bytes]:
            captured["cmd"] = cmd
            captured["cwd"] = str(cwd)
            captured["input"] = input_data
            captured["timeout"] = timeout_seconds
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=(
                    b'{"type":"assistant.message","data":{"content":"hello"}}\n'
                    b'{"type":"result","data":{"exitCode":0}}\n'
                ),
                stderr=b"",
            )

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)

        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=tmp_path, prompt="hi", model=None, timeout_seconds=3)
        )

        assert_model_equal(outcome, CliMutationOutcome(status="finished", result_text="hello", error_detail=None))
        assert captured == {
            "cmd": [
                "gh",
                "copilot",
                "--",
                "-p",
                "",
                "--output-format",
                "json",
                "--silent",
                "--allow-all-tools",
                "--allow-all-paths",
                "--allow-all-urls",
            ],
            "cwd": str(tmp_path),
            "input": b"hi",
            "timeout": 3,
        }

    def test_missing_gh_binary_returns_error_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing gh binary maps to an error outcome naming the GitHub CLI."""

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise FileNotFoundError("gh")

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)

        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=tmp_path, prompt="hi", model=None, timeout_seconds=3)
        )

        assert_model_equal(
            outcome,
            CliMutationOutcome(
                status="error",
                result_text=None,
                error_detail=(
                    "gh is not installed or not on PATH: gh. Fix: install the GitHub CLI (https://cli.github.com)"
                ),
            ),
        )

    def test_process_timeout_returns_timeout_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A subprocess timeout maps to a timeout outcome."""

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(cmd="gh", timeout=3)

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)

        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=tmp_path, prompt="hi", model=None, timeout_seconds=3)
        )

        assert_model_equal(outcome, CliMutationOutcome(status="timeout", result_text=None, error_detail=None))
