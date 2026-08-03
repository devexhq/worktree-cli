"""Tests for the Gemini CLI direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from getworktree.core.agents import (
    AgentRequest,
    AgentResponseStatus,
    GeminiAgentAdapter,
    get_agent_adapter,
)
from getworktree.core.agents.cli_mutation import (
    CliMutationOutcome,
    CliMutationRunRequest,
)
from getworktree.core.agents.gemini import (
    GEMINI_API_KEY_ENV,
    default_gemini_run,
    resolve_gemini_api_key,
)
from getworktree.core.loops.payload import AgentFailurePayload


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _payload() -> AgentFailurePayload:
    return AgentFailurePayload(
        command="pytest",
        args=["-q"],
        trigger_status="failed",
        exit_code=1,
        timed_out=False,
        duration_ms=10,
        stdout="boom",
        stderr="",
    )


def _request(sandbox: Path, **kwargs: object) -> AgentRequest:
    data: dict[str, object] = {
        "mode": "fix_failure",
        "payload": _payload(),
        "sandbox_path": sandbox,
        "timeout_seconds": 10,
        "model": "gemini-2.5-flash",
    }
    data.update(kwargs)
    return AgentRequest.model_validate(data)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GEMINI_API_KEY_ENV, "test-key")


class GeminiFactoryTests:
    def test_gemini_provider(self) -> None:
        adapter = get_agent_adapter("gemini")
        assert isinstance(adapter, GeminiAgentAdapter)


class GeminiAuthTests:
    def test_resolve_present(self) -> None:
        assert resolve_gemini_api_key({GEMINI_API_KEY_ENV: "abc"}) == "abc"

    def test_resolve_missing(self) -> None:
        assert resolve_gemini_api_key({}) is None

    def test_preflight_requires_key(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(GEMINI_API_KEY_ENV, raising=False)
        adapter = GeminiAgentAdapter(
            run_fn=lambda req: CliMutationOutcome(status="finished")
        )
        resp = adapter.propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any(GEMINI_API_KEY_ENV in err for err in resp.errors)


class GeminiRunTests:
    def test_default_run_parses_json(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, cwd, env, input, capture_output, text, shell, timeout, check):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["env_key"] = env[GEMINI_API_KEY_ENV]
            captured["input"] = input
            captured["timeout"] = timeout

            class Result:
                returncode = 0
                stdout = b'{"response": "pong"}'
                stderr = b""

            return Result()

        monkeypatch.setattr(subprocess, "run", fake_run)

        outcome = default_gemini_run(
            CliMutationRunRequest(
                sandbox_path=sandbox,
                prompt="hi",
                model="gemini-2.5-flash",
                timeout_seconds=3,
            )
        )

        assert outcome.status == "finished"
        assert outcome.result_text == "pong"
        assert captured["cwd"] == str(sandbox)
        assert captured["env_key"] == "test-key"
        assert captured["input"] == b"hi"
        assert "-m" in captured["cmd"]
        assert captured["cmd"][0:3] == ["gemini", "-p", ""]

    def test_missing_binary(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("gemini")

        monkeypatch.setattr(subprocess, "run", fake_run)
        outcome = default_gemini_run(
            CliMutationRunRequest(
                sandbox_path=sandbox, prompt="hi", model=None, timeout_seconds=3
            )
        )
        assert outcome.status == "error"
        assert "install the Gemini CLI" in (outcome.error_detail or "")

    def test_timeout(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gemini", timeout=3)

        monkeypatch.setattr(subprocess, "run", fake_run)
        outcome = default_gemini_run(
            CliMutationRunRequest(
                sandbox_path=sandbox, prompt="hi", model=None, timeout_seconds=3
            )
        )
        assert outcome.status == "timeout"


class GeminiAdapterTests:
    def test_proposed_patch(self, sandbox: Path) -> None:
        _git(["init"], cwd=sandbox)
        _git(["config", "user.email", "test@example.com"], cwd=sandbox)
        _git(["config", "user.name", "Test"], cwd=sandbox)
        (sandbox / "a.txt").write_text("original\n", encoding="utf-8")
        _git(["add", "-A"], cwd=sandbox)
        _git(["commit", "-m", "init"], cwd=sandbox)

        def run_fn(request: CliMutationRunRequest) -> CliMutationOutcome:
            (request.sandbox_path / "a.txt").write_text("fixed\n", encoding="utf-8")
            return CliMutationOutcome(status="finished", result_text="done")

        adapter = GeminiAgentAdapter(run_fn=run_fn)
        resp = adapter.propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.mutation_baseline_ref is not None
