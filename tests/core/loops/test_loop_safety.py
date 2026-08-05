"""Tests for loop safety helpers and controller integration."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from getworktree.core.config.models import WorktreeConfig
from getworktree.core.git_sandbox import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
)
from getworktree.core.loops.agents.base import (
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.loops.models import (
    LoopAgent,
    LoopApproval,
    LoopContext,
    LoopDefinition,
    LoopIteration,
    LoopPatch,
    LoopSandbox,
    LoopTrigger,
)
from getworktree.core.loops.patch import PatchApplyResult, PatchApplyStatus
from getworktree.core.loops.payload import AgentFailurePayload
from getworktree.core.loops.runner import LoopFinalStatus, run_loop_iteration
from getworktree.core.loops.safety import (
    NO_OP_STREAK_THRESHOLD,
    REPEAT_FAILURE_THRESHOLD,
    SafetyState,
    failure_signature,
    record_agent_status,
    record_trigger_failure,
    record_trigger_success,
    safety_stop_message,
    session_timed_out,
)
from getworktree.core.loops.trigger import TriggerRunResult, TriggerRunStatus


class FailureSignatureTests:
    def test_full_sha256_hex(self) -> None:
        sig = failure_signature("failed", 1, "stdout", "stderr")
        expected = hashlib.sha256(b"failed|1|stdout|stderr").hexdigest()
        assert sig == expected
        assert len(sig) == 64

    def test_whitespace_collapsed_and_tail(self) -> None:
        long = ("x" * 5000) + "  end"
        sig_a = failure_signature("failed", 2, long, "a\n\nb")
        # Manual canonical: last 4000 of collapsed stdout
        collapsed = " ".join(long.split())
        tail = collapsed[-4000:]
        canonical = f"failed|2|{tail}|a b"
        assert sig_a == hashlib.sha256(canonical.encode()).hexdigest()

    def test_none_exit_code(self) -> None:
        sig = failure_signature("timeout", None, "", "")
        # exit_code None → empty field → timeout||| (4 pipe-separated fields)
        assert sig == hashlib.sha256(b"timeout|||").hexdigest()

    def test_stable_identical_inputs(self) -> None:
        a = failure_signature("failed", 1, "out", "err")
        b = failure_signature("failed", 1, "out", "err")
        assert a == b


class SafetyStateHelperTests:
    def test_repeat_failure_trips_at_three(self) -> None:
        state = SafetyState()
        sig = "abc"
        assert (
            record_trigger_failure(state, signature=sig, detect_repeat_failures=True)
            is None
        )
        assert state.consecutive_failure_signatures == 1
        assert (
            record_trigger_failure(state, signature=sig, detect_repeat_failures=True)
            is None
        )
        assert (
            record_trigger_failure(state, signature=sig, detect_repeat_failures=True)
            == "repeat_failure_signature"
        )
        assert state.consecutive_failure_signatures == REPEAT_FAILURE_THRESHOLD

    def test_different_signature_resets(self) -> None:
        state = SafetyState()
        record_trigger_failure(state, signature="a", detect_repeat_failures=True)
        record_trigger_failure(state, signature="a", detect_repeat_failures=True)
        record_trigger_failure(state, signature="b", detect_repeat_failures=True)
        assert state.consecutive_failure_signatures == 1
        assert state.last_failure_signature == "b"

    def test_success_resets(self) -> None:
        state = SafetyState()
        record_trigger_failure(state, signature="a", detect_repeat_failures=True)
        record_trigger_success(state)
        assert state.consecutive_failure_signatures == 0
        assert state.last_failure_signature is None

    def test_detect_repeat_disabled(self) -> None:
        state = SafetyState()
        for _ in range(5):
            assert (
                record_trigger_failure(
                    state, signature="same", detect_repeat_failures=False
                )
                is None
            )
        assert state.consecutive_failure_signatures == 0

    def test_no_op_streak(self) -> None:
        state = SafetyState()
        assert record_agent_status(state, "no_op") is None
        assert record_agent_status(state, "no_op") == "agent_no_op_streak"
        assert state.consecutive_agent_no_ops == NO_OP_STREAK_THRESHOLD

    def test_non_no_op_resets(self) -> None:
        state = SafetyState()
        record_agent_status(state, "no_op")
        record_agent_status(state, "proposed_patch")
        assert state.consecutive_agent_no_ops == 0

    def test_session_timeout(self) -> None:
        state = SafetyState(session_started_monotonic=100.0)
        assert (
            session_timed_out(state, session_timeout_seconds=10, now_monotonic=109.0)
            is False
        )
        assert (
            session_timed_out(state, session_timeout_seconds=10, now_monotonic=110.0)
            is True
        )
        assert (
            session_timed_out(state, session_timeout_seconds=None, now_monotonic=999.0)
            is False
        )
        assert (
            session_timed_out(state, session_timeout_seconds=0, now_monotonic=999.0)
            is False
        )

    def test_stop_messages(self) -> None:
        assert "3x" in safety_stop_message("repeat_failure_signature")
        assert "no-op" in safety_stop_message("agent_no_op_streak")
        assert "900s" in safety_stop_message(
            "session_timeout", session_timeout_seconds=900
        )
        assert "aborted" in safety_stop_message("user_abort")


def _loop(max_attempts: int = 10) -> LoopDefinition:
    return LoopDefinition(
        version=1,
        name="fix-tests",
        description="test",
        trigger=LoopTrigger(command="true", args=[], timeout_seconds=10),
        agent=LoopAgent(provider="local", mode="fix_failure", timeout_seconds=10),
        iteration=LoopIteration(
            max_attempts=max_attempts,
            stop_when=["trigger_passes", "unfixable", "user_abort"],
        ),
        sandbox=LoopSandbox(auto_clean=False, keep_on_failure=True),
        approval=LoopApproval(require_before_apply=False),
        context=LoopContext(include=["trigger_output"]),
        patch=LoopPatch(strategy="unified_diff", max_files=10, max_patch_kb=64),
    )


def _config(**loop_overrides: object) -> WorktreeConfig:
    raw = WorktreeConfig(
        version=1,
        project={"name": "t"},
        approval={"require_before_apply": False, "require_before_final_apply": False},
        sandbox={
            "base_ref": "HEAD",
            "auto_clean": True,
            "keep_on_failure": True,
            "max_active_sandboxes": 3,
            "default_timeout_seconds": 900,
        },
    )
    if not loop_overrides:
        return raw
    loop_data = raw.loop.model_dump()
    loop_data.update(loop_overrides)
    return raw.model_copy(update={"loop": raw.loop.model_validate(loop_data)})


def _session(path: Path) -> SandboxSession:
    return SandboxSession(
        session_id="sbx_safe01",
        target_branch="worktree/sandbox-sbx_safe01",
        sandbox_path=path,
        base_commit="abc123def456",
        created_at="2026-01-01T00:00:00+00:00",
    )


def _trigger(
    status: TriggerRunStatus = TriggerRunStatus.FAILED,
    *,
    stdout: str = "same-out",
    stderr: str = "same-err",
    exit_code: int | None = 1,
) -> TriggerRunResult:
    return TriggerRunResult(
        status=status,
        command="true",
        args=[],
        cwd=Path("/tmp"),
        exit_code=0 if status == TriggerRunStatus.PASSED else exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=5,
    )


def _payload() -> AgentFailurePayload:
    return AgentFailurePayload(
        command="true",
        args=[],
        trigger_status="failed",
        exit_code=1,
        timed_out=False,
    )


class _FakeAgent:
    def __init__(self, responses: list[AgentResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def propose_fix(self, request: AgentRequest) -> AgentResponse:
        _ = request
        if self.calls >= len(self._responses):
            return AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


class SafetyControllerIntegrationTests:
    def test_repeat_failure_signature_stop(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sbx"
        sandbox.mkdir()
        triggers = [_trigger() for _ in range(5)]
        agent = _FakeAgent(
            [
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                )
                for _ in range(5)
            ]
        )
        result = run_loop_iteration(
            loop=_loop(max_attempts=10),
            cwd=tmp_path,
            config=_config(detect_repeat_failures=True),
            agent=agent,
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: triggers.pop(0) if triggers else _trigger(),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED, touched_files=["a.py"]
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "repeat_failure_signature"
        assert len(result.attempts) == REPEAT_FAILURE_THRESHOLD

    def test_repeat_disabled_continues(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sbx"
        sandbox.mkdir()
        agent = _FakeAgent(
            [AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)]
        )
        # With detect off, identical failures do not stop early; no-op streak
        # will stop at 2 agent no_ops instead of repeat signature at 3.
        call_n = {"n": 0}

        def trigger_fn(**_k: object) -> TriggerRunResult:
            call_n["n"] += 1
            return _trigger()

        result = run_loop_iteration(
            loop=_loop(max_attempts=5),
            cwd=tmp_path,
            config=_config(detect_repeat_failures=False),
            agent=agent,
            list_changed_files=lambda _p: [],
            run_trigger_fn=trigger_fn,
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
            detect_repeat_failures=False,
        )
        assert result.stop_reason == "agent_no_op_streak"
        assert result.status == LoopFinalStatus.FAILED

    def test_agent_no_op_streak_stop(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sbx"
        sandbox.mkdir()
        agent = _FakeAgent(
            [
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1),
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1),
            ]
        )
        # Distinct trigger outputs so repeat-failure does not trip first.
        outs = ["one", "two", "three"]

        def trigger_fn(**_k: object) -> TriggerRunResult:
            out = outs.pop(0) if outs else "more"
            return _trigger(stdout=out, stderr=out)

        result = run_loop_iteration(
            loop=_loop(max_attempts=5),
            cwd=tmp_path,
            config=_config(),
            agent=agent,
            list_changed_files=lambda _p: [],
            run_trigger_fn=trigger_fn,
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
        )
        assert result.stop_reason == "agent_no_op_streak"
        assert len(result.attempts) == NO_OP_STREAK_THRESHOLD

    def test_session_timeout_disabled_when_non_positive(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sbx"
        sandbox.mkdir()
        result = run_loop_iteration(
            loop=_loop(max_attempts=1),
            cwd=tmp_path,
            config=_config(),
            agent=_FakeAgent([]),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.PASSED),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
            session_timeout_seconds=0,
        )
        assert result.status == LoopFinalStatus.PASSED
        assert result.stop_reason == "trigger_passed"

    def test_session_timeout_before_agent(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sbx"
        sandbox.mkdir()

        def very_slow(**_k: object) -> TriggerRunResult:
            time.sleep(1.05)
            return _trigger()

        result = run_loop_iteration(
            loop=_loop(max_attempts=5),
            cwd=tmp_path,
            config=_config(),
            agent=_FakeAgent(
                [AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=very_slow,
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
            session_timeout_seconds=1,
        )
        # First attempt starts; after slow trigger, pre-agent checkpoint trips.
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "session_timeout"
        assert len(result.attempts) == 1
        assert result.attempts[0].agent_status is None
