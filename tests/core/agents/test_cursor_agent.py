"""Tests for the Cursor direct-mutation agent adapter."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import FileSystem
from worktree.core.agents import (
    AgentRequest,
    AgentResponseStatus,
    CursorAgentAdapter,
    get_agent_adapter,
)
from worktree.core.agents.cli_mutation import (
    CliMutationOutcome,
    CliMutationRunRequest,
    CliMutationRunStatus,
    build_mutation_prompt,
)
from worktree.core.agents.cursor import (
    CURSOR_API_KEY_ENV,
    cancel_cursor_run,
    cursor_outcome_from_result,
    default_cursor_run,
    resolve_cursor_api_key,
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
def sandbox(fs: FileSystem) -> Path:
    root = fs.base_path / "sandbox"
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
    status: CliMutationRunStatus = "finished",
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


class CursorOutcomeMappingTests:
    """Direct unit tests for Cursor SDK wait() outcome mapping."""

    @pytest.mark.parametrize(
        ("raw_status", "result_text", "expected_status", "expected_error_detail"),
        [
            pytest.param("finished", "patch applied", "finished", None, id="finished_with_text"),
            pytest.param("finished", None, "finished", None, id="finished_without_text"),
            pytest.param("cancelled", None, "timeout", None, id="cancelled_maps_to_timeout"),
            pytest.param("timeout", "timeout text", "timeout", None, id="timeout_status"),
            pytest.param("error", "token limit", "error", "token limit", id="error_with_detail"),
            pytest.param("error", None, "error", "error", id="error_fallback_detail"),
            pytest.param("expired", "session ended", "error", "session ended", id="expired_with_detail"),
            pytest.param("expired", None, "error", "expired", id="expired_fallback_detail"),
            pytest.param(
                "unknown_state",
                "txt",
                "error",
                "unrecognized Cursor run status 'unknown_state'",
                id="unrecognized_status",
            ),
        ],
    )
    def test_cursor_outcome_from_result_maps_status_and_text(
        self,
        raw_status: str,
        result_text: str | None,
        expected_status: str,
        expected_error_detail: str | None,
    ) -> None:
        """Map raw Cursor SDK result object into CliMutationOutcome."""
        dummy = SimpleNamespace(status=raw_status, result=result_text)
        outcome = cursor_outcome_from_result(dummy)
        assert outcome.status == expected_status
        assert outcome.result_text == result_text
        assert outcome.error_detail == expected_error_detail


class CancelCursorRunTests:
    """Tests for best-effort cancel_cursor_run."""

    def test_callable_cancel_is_invoked(self) -> None:
        """Call cancel() method on run handle when present."""
        cancelled = False

        class _Run:
            def cancel(self) -> None:
                nonlocal cancelled
                cancelled = True

        cancel_cursor_run(_Run())
        assert cancelled is True

    def test_failing_cancel_does_not_raise(self) -> None:
        """Swallow exceptions raised by run.cancel()."""

        class _FailingRun:
            def cancel(self) -> None:
                raise RuntimeError("SDK cancel failed")

        cancel_cursor_run(_FailingRun())

    def test_missing_or_non_callable_cancel_does_not_raise(self) -> None:
        """Ignore objects without a callable cancel method."""
        cancel_cursor_run(object())
        cancel_cursor_run(SimpleNamespace(cancel="not-callable"))


class BuildPromptTests:
    def test_includes_mode_and_payload(self, sandbox: Path) -> None:
        prompt = build_mutation_prompt(_request(sandbox))
        assert "fix_failure" in prompt
        assert "pytest" in prompt
        assert "boom" in prompt
        assert str(sandbox) in prompt


class CursorAdapterTests:
    def test_proposed_patch(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("worktree.core.agents.cursor.default_cursor_run", _fake_run(edits={"a.txt": "fixed\n"}))
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROPOSED_PATCH
        assert resp.ok
        assert resp.unified_diff is not None
        assert "fixed" in resp.unified_diff
        assert resp.mutation_baseline_ref is not None
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "fixed\n"

    def test_no_op_when_no_edits(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("worktree.core.agents.cursor.default_cursor_run", _fake_run())
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.NO_OP
        assert resp.mutation_baseline_ref is not None

    def test_missing_model(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("worktree.core.agents.cursor.default_cursor_run", _fake_run())
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox, model=None))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("model" in e.lower() for e in resp.errors)
        assert resp.mutation_baseline_ref is None

    def test_missing_api_key(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CURSOR_API_KEY_ENV, raising=False)
        monkeypatch.setattr("worktree.core.agents.cursor.default_cursor_run", _fake_run())
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any(CURSOR_API_KEY_ENV in e for e in resp.errors)
        assert resp.mutation_baseline_ref is None

    def test_sdk_error_status(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "worktree.core.agents.cursor.default_cursor_run", _fake_run(status="error", error_detail="auth failed")
        )
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("auth failed" in e for e in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_timeout(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("worktree.core.agents.cursor.default_cursor_run", _fake_run(status="timeout"))
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox))

        assert resp.status == AgentResponseStatus.TIMEOUT
        assert any("timed out" in e.lower() for e in resp.errors)
        assert resp.mutation_baseline_ref is not None

    def test_gate_violation_discards_edits(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "worktree.core.agents.cursor.default_cursor_run",
            _fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}),
        )
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        assert any("max_files" in e for e in resp.errors)
        # Sandbox restored to baseline: agent edits discarded.
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "original\n"
        assert not (sandbox / "b.txt").exists()

    def test_gate_violation_preserves_wip(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (sandbox / "a.txt").write_text("wip content\n", encoding="utf-8")
        monkeypatch.setattr(
            "worktree.core.agents.cursor.default_cursor_run",
            _fake_run(edits={"a.txt": "edit one\n", "b.txt": "edit two\n"}),
        )
        adapter = CursorAgentAdapter()

        resp = adapter.propose_fix(_request(sandbox, max_files=1))

        assert resp.status == AgentResponseStatus.PROVIDER_ERROR
        # Discard must restore the WIP overlay, not the committed tip.
        assert (sandbox / "a.txt").read_text(encoding="utf-8") == "wip content\n"
        assert not (sandbox / "b.txt").exists()


class DefaultCursorRunTests:
    def test_missing_sdk_is_provider_error(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "cursor_sdk", None)
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
        assert "src[cursor]" in outcome.error_detail

    def test_missing_api_key_returns_provider_error(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return provider error outcome when CURSOR_API_KEY is not set."""
        monkeypatch.delenv(CURSOR_API_KEY_ENV, raising=False)
        fake_sdk = SimpleNamespace(
            Agent=object,
            AgentOptions=object,
            LocalAgentOptions=object,
        )
        monkeypatch.setitem(sys.modules, "cursor_sdk", fake_sdk)
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
        assert "missing CURSOR_API_KEY" in outcome.error_detail

    def test_thread_worker_timeout_invokes_cancel_and_returns_timeout(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Return timeout outcome and cancel run handle when worker thread times out."""
        cancelled = False
        event = threading.Event()

        class _FakeRun:
            def wait(self) -> object:
                event.wait(timeout=1.0)
                return SimpleNamespace(status="finished", result="done")

            def cancel(self) -> None:
                nonlocal cancelled
                cancelled = True
                event.set()

        class _FakeAgent:
            def __enter__(self) -> _FakeAgent:
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def send(self, prompt: str) -> _FakeRun:
                return _FakeRun()

            @classmethod
            def create(cls, options: object) -> _FakeAgent:
                return cls()

        fake_sdk = SimpleNamespace(
            Agent=_FakeAgent,
            AgentOptions=lambda **kw: kw,
            LocalAgentOptions=lambda **kw: kw,
        )
        monkeypatch.setitem(sys.modules, "cursor_sdk", fake_sdk)
        outcome = default_cursor_run(
            CliMutationRunRequest(
                model="composer-2.5",
                sandbox_path=sandbox,
                prompt="fix it",
                timeout_seconds=0.01,
            )
        )
        assert outcome.status == "timeout"
        assert cancelled is True

    def test_thread_worker_exception_returns_error_outcome(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Return error outcome with exception detail when worker thread raises."""
        fake_sdk = SimpleNamespace(
            Agent=object,
            AgentOptions=object,
            LocalAgentOptions=object,
        )
        monkeypatch.setitem(sys.modules, "cursor_sdk", fake_sdk)
        monkeypatch.setattr(
            "worktree.core.agents.cursor._run_cursor_agent_thread",
            lambda *a, **kw: {"exception": RuntimeError("socket closed")},
        )
        outcome = default_cursor_run(
            CliMutationRunRequest(
                model="composer-2.5",
                sandbox_path=sandbox,
                prompt="fix it",
                timeout_seconds=1.0,
            )
        )
        assert outcome.status == "error"
        assert outcome.error_detail == "socket closed"

    def test_thread_worker_missing_result_returns_error_outcome(
        self, sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Return error outcome when worker finishes without a result object."""
        fake_sdk = SimpleNamespace(
            Agent=object,
            AgentOptions=object,
            LocalAgentOptions=object,
        )
        monkeypatch.setitem(sys.modules, "cursor_sdk", fake_sdk)
        monkeypatch.setattr(
            "worktree.core.agents.cursor._run_cursor_agent_thread",
            lambda *a, **kw: {},
        )
        outcome = default_cursor_run(
            CliMutationRunRequest(
                model="composer-2.5",
                sandbox_path=sandbox,
                prompt="fix it",
                timeout_seconds=1.0,
            )
        )
        assert outcome.status == "error"
        assert outcome.error_detail == "no run result"
