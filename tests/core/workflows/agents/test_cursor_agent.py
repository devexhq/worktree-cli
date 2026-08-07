"""Tests for the Cursor direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from getworktree.core.workflows.agents import (
    AgentRequest,
    AgentResponseStatus,
    CursorAgentAdapter,
    get_agent_adapter,
)
from getworktree.core.workflows.agents.cli_mutation import (
    CliMutationOutcome,
    CliMutationRunRequest,
    build_mutation_prompt,
)
from getworktree.core.workflows.agents.cursor import (
    CURSOR_API_KEY_ENV,
    default_cursor_run,
    resolve_cursor_api_key,
)
from getworktree.core.workflows.payload import AgentFailurePayload


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
    base: dict[str, object] = {
        "mode": "fix_failure",
        "payload": _payload(),
        "sandbox_path": sandbox,
        "timeout_seconds": 10,
        "model": "composer-2.5",
    }
    base.update(kwargs)
    return AgentRequest.model_validate(base)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    _git(["init"], cwd=root)
    _git(["config", "user.email", "test@example.com"], cwd=root)
    _git(["config", "user.name", "Test"], cwd=root)
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    _git(["add", "-A"], cwd=root)
    _git(["commit", "-m", "init"], cwd=root)
    return root


@pytest.fixture(autouse=True)
def _cursor_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CURSOR_API_KEY_ENV, "test-key")


def _fake_run(
    *,
    edits: dict[str, str] | None = None,
    status: str = "finished",
    error_detail: str | None = None,
    result_text: str | None = "done",
):
    def _run(request: CliMutationRunRequest) -> CliMutationOutcome:
        if edits:
            cwd = request.sandbox_path
            for rel, content in edits.items():
                path = cwd / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        return CliMutationOutcome(status=status, result_text=result_text, error_detail=error_detail)

    return _run


class FactoryCursorTests:
    def test_cursor_provider(self) -> None:
        adapter = get_agent_adapter("cursor")
        assert isinstance(adapter, CursorAgentAdapter)

    def test_unsupported_lists_cursor(self) -> None:
        with pytest.raises(ValueError, match="AGENT_PROVIDER_UNSUPPORTED") as exc:
            get_agent_adapter("openai")
        msg = str(exc.value)
        assert "local" in msg
        assert "ollama" in msg
        assert "cursor" in msg


class ResolveApiKeyTests:
    def test_present(self) -> None:
        assert resolve_cursor_api_key({CURSOR_API_KEY_ENV: "abc"}) == "abc"

    def test_missing(self) -> None:
        assert resolve_cursor_api_key({}) is None

    def test_blank(self) -> None:
        assert resolve_cursor_api_key({CURSOR_API_KEY_ENV: "   "}) is None


class BuildPromptTests:
    def test_includes_mode_and_payload(self, sandbox: Path) -> None:
        prompt = build_mutation_prompt(_request(sandbox))
        assert "fix_failure" in prompt
        assert "pytest" in prompt
        assert "boom" in prompt
        assert str(sandbox) in prompt


class CursorAdapterTests:
    def test_proposed_patch(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run(edits={"a.txt": "fixed\n"}))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.unified_diff is not None
        assert "fixed" in resp.unified_diff
        assert resp.mutation_baseline_ref is not None
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_no_op_when_no_edits(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.NO_OP
        assert resp.mutation_baseline_ref is not None

    def test_missing_model(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(_request(sandbox, model=None))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("model" in e.lower() for e in resp.errors)
        assert resp.mutation_baseline_ref is None

    def test_missing_api_key(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CURSOR_API_KEY_ENV, raising=False)
        adapter = CursorAgentAdapter(run_fn=_fake_run())

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any(CURSOR_API_KEY_ENV in e for e in resp.errors)
        assert resp.mutation_baseline_ref is None

    def test_sdk_error_status(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run(status="error", error_detail="auth failed"))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("auth failed" in e for e in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_timeout(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run(status="timeout"))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.TIMEOUT
        assert any("timed out" in e.lower() for e in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_cancelled_maps_to_timeout(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run(status="timeout"))

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.TIMEOUT

    def test_gate_violation_discards_edits(self, sandbox: Path) -> None:
        adapter = CursorAgentAdapter(run_fn=_fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}))

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("max_files" in e for e in resp.errors)
        # Sandbox restored to baseline: agent edits discarded.
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (sandbox / "b.txt").exists()

    def test_gate_violation_preserves_wip(self, sandbox: Path) -> None:
        (sandbox / "a.txt").write_text("wip content\n", encoding="utf-8")
        adapter = CursorAgentAdapter(run_fn=_fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}))

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        # Discard must restore the WIP overlay, not the committed tip.
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "wip content\n"
        assert not (sandbox / "b.txt").exists()


class DefaultCursorRunTests:
    def test_missing_sdk_is_provider_error(self, sandbox: Path) -> None:
        outcome = default_cursor_run(
            CliMutationRunRequest(
                model="composer-2.5",
                sandbox_path=sandbox,
                prompt="fix it",
                timeout_seconds=1.0,
            )
        )
        assert outcome.status == "error"
        assert outcome.error_detail is not None
        assert "getworktree[cursor]" in outcome.error_detail
