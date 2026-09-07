"""Tests for the Copilot CLI direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FileSystem
from worktree.core.agents import (
    AgentRequest,
    AgentResponseStatus,
    CopilotAgentAdapter,
)
from worktree.core.agents.cli_mutation import (
    CliMutationOutcome,
    CliMutationRunRequest,
)
from worktree.core.agents.copilot import (
    default_copilot_run,
    resolve_copilot_token,
)
from worktree.core.agents.models import AgentFailurePayload


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
    }
    data.update(kwargs)
    return AgentRequest.model_validate(data)


@pytest.fixture
def sandbox(fs: FileSystem) -> Path:
    root = fs.base_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")


class CopilotAuthTests:
    def test_resolve_present(self) -> None:
        assert resolve_copilot_token({"GH_TOKEN": "abc"}) == "abc"
        assert resolve_copilot_token({"GITHUB_TOKEN": "xyz"}) == "xyz"

    def test_resolve_missing(self) -> None:
        assert resolve_copilot_token({}) is None

    def test_preflight_requires_token(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        adapter = CopilotAgentAdapter()
        resp = adapter.propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("GH_TOKEN" in err for err in resp.errors)


class CopilotRunTests:
    def test_default_run_parses_jsonl(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_run(cmd, *, cwd, env, input_data, timeout_seconds, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = str(cwd)
            captured["input"] = input_data
            captured["timeout"] = timeout_seconds

            class Result:
                returncode = 0
                stdout = b'{"type":"assistant.message","data":{"content":"hello"}}\n{"type":"result","data":{"exitCode":0}}\n'
                stderr = b""

            return Result()

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)

        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=sandbox, prompt="hi", model=None, timeout_seconds=3)
        )

        assert outcome.status == "finished"
        assert outcome.result_text == "hello"
        assert captured["cwd"] == str(sandbox)
        assert captured["input"] == b"hi"
        assert captured["cmd"][0] == "gh"
        assert captured["cmd"][0:3] == ["gh", "copilot", "--"]
        assert captured["cmd"][3:6] == ["-p", "", "--output-format"]

    def test_missing_binary(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("gh")

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)
        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=sandbox, prompt="hi", model=None, timeout_seconds=3)
        )
        assert outcome.status == "error"
        assert "GitHub CLI" in (outcome.error_detail or "")

    def test_timeout(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=3)

        monkeypatch.setattr("worktree.core.agents.copilot.run_isolated_process", fake_run)
        outcome = default_copilot_run(
            CliMutationRunRequest(sandbox_path=sandbox, prompt="hi", model=None, timeout_seconds=3)
        )
        assert outcome.status == "timeout"


class CopilotAdapterTests:
    def test_no_op(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _git(["init"], cwd=sandbox)
        _git(["config", "user.email", "test@example.com"], cwd=sandbox)
        _git(["config", "user.name", "Test"], cwd=sandbox)
        (sandbox / "a.txt").write_text("original\n", encoding="utf-8")
        _git(["add", "-A"], cwd=sandbox)
        _git(["commit", "-m", "init"], cwd=sandbox)

        monkeypatch.setattr(
            "worktree.core.agents.copilot.default_copilot_run",
            lambda _req: CliMutationOutcome(status="finished", result_text="done"),
        )

        adapter = CopilotAgentAdapter()
        resp = adapter.propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.NO_OP
        assert resp.mutation_baseline_ref is not None

    def test_proposed_patch(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Capture diff and propose patch when Copilot run succeeds with edits."""
        _git(["init"], cwd=sandbox)
        _git(["config", "user.email", "test@example.com"], cwd=sandbox)
        _git(["config", "user.name", "Test"], cwd=sandbox)
        (sandbox / "a.txt").write_text("original\n", encoding="utf-8")
        _git(["add", "-A"], cwd=sandbox)
        _git(["commit", "-m", "init"], cwd=sandbox)

        def fake_copilot_run(request: CliMutationRunRequest) -> CliMutationOutcome:
            (request.sandbox_path / "a.txt").write_text("fixed\n", encoding="utf-8")
            return CliMutationOutcome(status="finished", result_text="done")

        monkeypatch.setattr("worktree.core.agents.copilot.default_copilot_run", fake_copilot_run)
        adapter = CopilotAgentAdapter()
        resp = adapter.propose_fix(_request(sandbox))
        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.unified_diff is not None
        assert "fixed" in resp.unified_diff
        assert resp.mutation_baseline_ref is not None
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_gate_violation_discards_edits(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Discard agent edits and restore sandbox on gate violation."""
        _git(["init"], cwd=sandbox)
        _git(["config", "user.email", "test@example.com"], cwd=sandbox)
        _git(["config", "user.name", "Test"], cwd=sandbox)
        (sandbox / "a.txt").write_text("original\n", encoding="utf-8")
        _git(["add", "-A"], cwd=sandbox)
        _git(["commit", "-m", "init"], cwd=sandbox)

        def fake_copilot_run(request: CliMutationRunRequest) -> CliMutationOutcome:
            (request.sandbox_path / "a.txt").write_text("edit 1\n", encoding="utf-8")
            (request.sandbox_path / "b.txt").write_text("edit 2\n", encoding="utf-8")
            return CliMutationOutcome(status="finished", result_text="done")

        monkeypatch.setattr("worktree.core.agents.copilot.default_copilot_run", fake_copilot_run)
        adapter = CopilotAgentAdapter()
        resp = adapter.propose_fix(_request(sandbox, max_files=1))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("max_files" in err for err in resp.errors)
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (sandbox / "b.txt").exists()

    def test_gate_violation_preserves_wip(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Preserve pre-existing uncommitted WIP when Copilot edits are rejected by gate."""
        _git(["init"], cwd=sandbox)
        _git(["config", "user.email", "test@example.com"], cwd=sandbox)
        _git(["config", "user.name", "Test"], cwd=sandbox)
        (sandbox / "a.txt").write_text("original\n", encoding="utf-8")
        _git(["add", "-A"], cwd=sandbox)
        _git(["commit", "-m", "init"], cwd=sandbox)
        (sandbox / "a.txt").write_text("wip content\n", encoding="utf-8")

        def fake_copilot_run(request: CliMutationRunRequest) -> CliMutationOutcome:
            (request.sandbox_path / "a.txt").write_text("edit 1\n", encoding="utf-8")
            (request.sandbox_path / "b.txt").write_text("edit 2\n", encoding="utf-8")
            return CliMutationOutcome(status="finished", result_text="done")

        monkeypatch.setattr("worktree.core.agents.copilot.default_copilot_run", fake_copilot_run)
        adapter = CopilotAgentAdapter()
        resp = adapter.propose_fix(_request(sandbox, max_files=1))
        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("max_files" in err for err in resp.errors)
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "wip content\n"
        assert not (sandbox / "b.txt").exists()
