"""Tests for the loop iteration controller."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from getworktree.core.agents.base import (
    AgentRequest,
    AgentResponse,
    AgentResponseStatus,
)
from getworktree.core.config.models import WorktreeConfig
from getworktree.core.git_sandbox import (
    SandboxCreateResult,
    SandboxCreateStatus,
    SandboxSession,
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
from getworktree.core.loops.runner import (
    LoopFinalStatus,
    resolve_max_attempts,
    run_loop_iteration,
)
from getworktree.core.loops.trigger import TriggerRunResult, TriggerRunStatus


def _loop(
    *,
    max_attempts: int = 3,
    require_before_apply: bool = False,
    stop_when: list[str] | None = None,
    auto_clean: bool = False,
    keep_on_failure: bool = True,
    provider: str = "local",
) -> LoopDefinition:
    return LoopDefinition(
        version=1,
        name="fix-tests",
        description="test loop",
        trigger=LoopTrigger(command="true", args=[], timeout_seconds=10),
        agent=LoopAgent(provider=provider, mode="fix_failure", timeout_seconds=10),
        iteration=LoopIteration(
            max_attempts=max_attempts,
            stop_when=stop_when or ["trigger_passes", "unfixable", "user_abort"],
        ),
        sandbox=LoopSandbox(auto_clean=auto_clean, keep_on_failure=keep_on_failure),
        approval=LoopApproval(require_before_apply=require_before_apply),
        context=LoopContext(include=["trigger_output"]),
        patch=LoopPatch(strategy="unified_diff", max_files=10, max_patch_kb=64),
    )


def _config(**loop_overrides: object) -> WorktreeConfig:
    raw = WorktreeConfig(
        version=1,
        project={"name": "t"},
        approval={"require_before_apply": False, "require_before_final_apply": False},
    )
    if not loop_overrides:
        return raw
    loop_data = raw.loop.model_dump()
    loop_data.update(loop_overrides)
    return raw.model_copy(update={"loop": raw.loop.model_validate(loop_data)})


def _session(path: Path, sid: str = "sbx_test01") -> SandboxSession:
    return SandboxSession(
        session_id=sid,
        target_branch=f"worktree/sandbox-{sid}",
        sandbox_path=path,
        base_commit="abc123def456",
        created_at="2026-01-01T00:00:00+00:00",
    )


def _trigger(
    status: TriggerRunStatus = TriggerRunStatus.FAILED,
    *,
    exit_code: int | None = 1,
    stdout: str = "out",
    stderr: str = "err",
) -> TriggerRunResult:
    return TriggerRunResult(
        status=status,
        command="true",
        args=[],
        cwd=Path("/tmp"),
        exit_code=exit_code if status != TriggerRunStatus.PASSED else 0,
        stdout=stdout,
        stderr=stderr,
        duration_ms=12,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        errors=[] if status == TriggerRunStatus.PASSED else ["trigger failed"],
    )


def _payload() -> AgentFailurePayload:
    return AgentFailurePayload(
        command="true",
        args=[],
        trigger_status="failed",
        exit_code=1,
        timed_out=False,
        duration_ms=12,
    )


class _FakeAgent:
    def __init__(self, responses: list[AgentResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.requests: list[AgentRequest] = []

    def propose_fix(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        if self.calls >= len(self._responses):
            return AgentResponse(
                status=AgentResponseStatus.PROVIDER_ERROR,
                errors=["no more fake responses"],
            )
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    path = tmp_path / "sbx"
    path.mkdir()
    return path


def _run(
    *,
    sandbox: Path,
    loop: LoopDefinition | None = None,
    config: WorktreeConfig | None = None,
    triggers: list[TriggerRunResult] | None = None,
    agent_responses: list[AgentResponse] | None = None,
    patch_results: list[PatchApplyResult] | None = None,
    approve_patch=None,
    abort_event: threading.Event | None = None,
    is_aborted=None,
    caller_max_attempts: int | None = None,
    create_status: SandboxCreateStatus = SandboxCreateStatus.OK,
    create_errors: list[str] | None = None,
    require_before_apply: bool | None = None,
    discard_mutation_fn=None,
    spy: dict[str, list] | None = None,
    prompt_dump_dir: Path | None = None,
):
    loop = loop or _loop()
    config = config or _config()
    trigger_queue = list(triggers or [])
    patch_queue = list(patch_results or [])
    cleaned: list[SandboxSession] = []

    def create_fn() -> SandboxCreateResult:
        if create_status != SandboxCreateStatus.OK:
            return SandboxCreateResult(
                status=create_status,
                errors=list(create_errors or ["create failed"]),
            )
        return SandboxCreateResult(
            status=SandboxCreateStatus.OK,
            session=_session(sandbox),
        )

    def trigger_fn(**kwargs):
        _ = kwargs
        if not trigger_queue:
            return _trigger(TriggerRunStatus.FAILED)
        return trigger_queue.pop(0)

    def patch_fn(**kwargs):
        if spy is not None:
            spy.setdefault("patch_calls", []).append(kwargs)
        if not patch_queue:
            return PatchApplyResult(
                status=PatchApplyStatus.APPLIED, touched_files=["a.py"]
            )
        return patch_queue.pop(0)

    def payload_fn(**kwargs):
        _ = kwargs
        return _payload()

    agent = _FakeAgent(
        agent_responses
        or [
            AgentResponse(
                status=AgentResponseStatus.PROPOSED_PATCH,
                unified_diff="diff --git a/a.py b/a.py\n",
                duration_ms=5,
            )
        ]
    )

    def _discard_fn(path: Path, baseline: str) -> None:
        if spy is not None:
            spy.setdefault("discard_calls", []).append((path, baseline))
        if discard_mutation_fn is not None:
            discard_mutation_fn(path, baseline)

    result = run_loop_iteration(
        loop=loop,
        cwd=sandbox.parent,
        config=config,
        caller_max_attempts=caller_max_attempts,
        abort_event=abort_event,
        is_aborted=is_aborted,
        approve_patch=approve_patch,
        agent=agent,
        list_changed_files=lambda _p: [],
        run_trigger_fn=trigger_fn,
        apply_patch_fn=patch_fn,
        discard_mutation_fn=_discard_fn,
        build_payload_fn=payload_fn,
        create_sandbox_fn=create_fn,
        cleanup_sandbox_fn=cleaned.append,
        require_before_apply=require_before_apply,
        prompt_dump_dir=prompt_dump_dir,
    )
    return result, agent, cleaned


class ResolveMaxAttemptsTests:
    def test_loop_value_clamped_by_hard_limit(self) -> None:
        cfg = _config(max_attempts_hard_limit=4)
        loop = _loop(max_attempts=10)
        assert resolve_max_attempts(loop=loop, config=cfg) == 4

    def test_caller_override(self) -> None:
        cfg = _config(max_attempts_hard_limit=20, default_max_attempts=5)
        loop = _loop(max_attempts=3)
        assert resolve_max_attempts(loop=loop, config=cfg, caller_max_attempts=7) == 7

    def test_caller_clamped(self) -> None:
        cfg = _config(max_attempts_hard_limit=2)
        loop = _loop(max_attempts=9)
        assert resolve_max_attempts(loop=loop, config=cfg, caller_max_attempts=5) == 2


class RunLoopIterationTests:
    def test_passed_first_trigger(self, sandbox: Path) -> None:
        result, agent, cleaned = _run(
            sandbox=sandbox,
            triggers=[_trigger(TriggerRunStatus.PASSED)],
        )
        assert result.ok
        assert result.status == LoopFinalStatus.PASSED
        assert result.stop_reason == "trigger_passed"
        assert result.session_id == "sbx_test01"
        assert len(result.attempts) == 1
        assert result.attempts[0].trigger_status == "passed"
        assert result.attempts[0].agent_status is None
        assert agent.calls == 0
        # auto_clean false → retain, no cleanup
        assert cleaned == []
        assert result.sandbox_retained is True

    def test_failed_max_attempts(self, sandbox: Path) -> None:
        # Use provider_error (not no_op) so safety no-op streak does not trip first.
        result, agent, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2),
            triggers=[
                _trigger(TriggerRunStatus.FAILED, stdout="a", stderr="a"),
                _trigger(TriggerRunStatus.FAILED, stdout="b", stderr="b"),
            ],
            agent_responses=[
                AgentResponse(status=AgentResponseStatus.PROVIDER_ERROR, duration_ms=1),
                AgentResponse(status=AgentResponseStatus.PROVIDER_ERROR, duration_ms=1),
            ],
        )
        assert not result.ok
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "max_attempts_exhausted"
        assert len(result.attempts) == 2
        assert agent.calls == 2
        assert result.max_attempts == 2

    def test_unfixable_stops(self, sandbox: Path) -> None:
        result, _, _ = _run(
            sandbox=sandbox,
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.UNFIXABLE,
                    unfixable_reason="cannot fix",
                    duration_ms=2,
                )
            ],
        )
        assert result.status == LoopFinalStatus.UNFIXABLE
        assert result.stop_reason == "agent_unfixable"
        assert len(result.attempts) == 1
        assert result.attempts[0].agent_status == "unfixable"

    def test_unfixable_continues_when_not_in_stop_when(self, sandbox: Path) -> None:
        result, agent, _ = _run(
            sandbox=sandbox,
            loop=_loop(
                max_attempts=2,
                stop_when=["trigger_passes", "user_abort"],
            ),
            triggers=[
                _trigger(TriggerRunStatus.FAILED),
                _trigger(TriggerRunStatus.FAILED),
            ],
            agent_responses=[
                AgentResponse(status=AgentResponseStatus.UNFIXABLE, duration_ms=1),
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1),
            ],
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "max_attempts_exhausted"
        assert agent.calls == 2

    def test_abort_before_attempt(self, sandbox: Path) -> None:
        event = threading.Event()
        event.set()
        result, agent, _ = _run(
            sandbox=sandbox,
            abort_event=event,
            triggers=[_trigger(TriggerRunStatus.PASSED)],
        )
        assert result.status == LoopFinalStatus.ABORTED
        assert result.stop_reason == "user_abort"
        assert result.attempts == []
        assert agent.calls == 0

    def test_abort_after_failed_trigger(self, sandbox: Path) -> None:
        event = threading.Event()

        def trigger_fn(**kwargs):
            _ = kwargs
            event.set()
            return _trigger(TriggerRunStatus.FAILED)

        result = run_loop_iteration(
            loop=_loop(),
            cwd=sandbox.parent,
            config=_config(),
            abort_event=event,
            agent=_FakeAgent([]),
            list_changed_files=lambda _p: [],
            run_trigger_fn=trigger_fn,
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK,
                session=_session(sandbox),
            ),
            cleanup_sandbox_fn=lambda _s: None,
        )
        assert result.status == LoopFinalStatus.ABORTED
        assert result.stop_reason == "user_abort"
        assert len(result.attempts) == 1
        assert result.attempts[0].agent_status is None

    def test_patch_apply_then_pass(self, sandbox: Path) -> None:
        result, agent, _ = _run(
            sandbox=sandbox,
            triggers=[
                _trigger(TriggerRunStatus.FAILED),
                _trigger(TriggerRunStatus.PASSED),
            ],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                    duration_ms=3,
                )
            ],
            patch_results=[
                PatchApplyResult(
                    status=PatchApplyStatus.APPLIED,
                    touched_files=["a.py"],
                )
            ],
        )
        assert result.status == LoopFinalStatus.PASSED
        assert result.stop_reason == "trigger_passed"
        assert len(result.attempts) == 2
        assert result.attempts[0].patch_status == "applied"
        assert result.attempts[0].patch_touched_files == ["a.py"]
        assert agent.calls == 1

    def test_patch_conflict_continues(self, sandbox: Path) -> None:
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2),
            triggers=[
                _trigger(TriggerRunStatus.FAILED),
                _trigger(TriggerRunStatus.FAILED),
            ],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                ),
                AgentResponse(status=AgentResponseStatus.NO_OP),
            ],
            patch_results=[
                PatchApplyResult(
                    status=PatchApplyStatus.CONFLICT,
                    errors=["conflict"],
                )
            ],
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.attempts[0].patch_status == "conflict"
        assert len(result.attempts) == 2

    def test_approval_rejected(self, sandbox: Path) -> None:
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1, require_before_apply=True),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                )
            ],
            approve_patch=lambda _diff: False,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.attempts[0].patch_status == "approval_rejected"

    def test_approval_callback_missing(self, sandbox: Path) -> None:
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2, require_before_apply=True),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                )
            ],
            approve_patch=None,
            require_before_apply=True,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "configuration_error"
        assert result.attempts[0].patch_status == "approval_callback_missing"
        assert any("approval_callback_missing" in e for e in result.errors)

    def test_sandbox_create_failed(self, sandbox: Path) -> None:
        result, agent, _ = _run(
            sandbox=sandbox,
            create_status=SandboxCreateStatus.CAPACITY_EXCEEDED,
            create_errors=["capacity"],
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "sandbox_create_failed"
        assert result.attempts == []
        assert result.errors == ["capacity"]
        assert agent.calls == 0

    def test_hard_limit_clamp_on_run(self, sandbox: Path) -> None:
        result, agent, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=50),
            config=_config(max_attempts_hard_limit=1),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)
            ],
        )
        assert result.max_attempts == 1
        assert len(result.attempts) == 1
        assert agent.calls == 1
        assert result.stop_reason == "max_attempts_exhausted"

    def test_trigger_spawn_failure_counts_attempt(self, sandbox: Path) -> None:
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1),
            triggers=[_trigger(TriggerRunStatus.SPAWN_FAILED, exit_code=None)],
            agent_responses=[
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)
            ],
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.attempts[0].trigger_status == "spawn_failed"

    def test_cleanup_on_pass_when_auto_clean(self, sandbox: Path) -> None:
        result, _, cleaned = _run(
            sandbox=sandbox,
            loop=_loop(auto_clean=True, keep_on_failure=True),
            triggers=[_trigger(TriggerRunStatus.PASSED)],
        )
        assert result.status == LoopFinalStatus.PASSED
        assert len(cleaned) == 1
        assert result.sandbox_retained is False
        assert result.sandbox_path is None

    def test_on_event_callbacks(self, sandbox: Path) -> None:
        events: list[tuple[str, dict]] = []

        def on_event(name: str, payload: dict) -> None:
            events.append((name, payload))

        run_loop_iteration(
            loop=_loop(max_attempts=1),
            cwd=sandbox.parent,
            config=_config(),
            agent=_FakeAgent(
                [AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.FAILED),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK,
                session=_session(sandbox),
            ),
            cleanup_sandbox_fn=lambda _s: None,
            on_event=on_event,
        )
        names = [n for n, _ in events]
        assert names[0] == "session_start"
        assert "attempt_start" in names
        assert "trigger_start" in names
        assert "trigger" in names
        assert "agent_start" in names
        assert "agent" in names
        assert names.index("trigger_start") < names.index("trigger")
        assert names.index("agent_start") < names.index("agent")

    def test_on_event_payloads_carry_error_detail(self, sandbox: Path) -> None:
        events: dict[str, dict] = {}

        def on_event(name: str, payload: dict) -> None:
            events[name] = payload

        run_loop_iteration(
            loop=_loop(max_attempts=1),
            cwd=sandbox.parent,
            config=_config(),
            agent=_FakeAgent(
                [
                    AgentResponse(
                        status=AgentResponseStatus.PROVIDER_ERROR,
                        duration_ms=1,
                        errors=["missing CURSOR_API_KEY"],
                    )
                ]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.FAILED),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK,
                session=_session(sandbox),
            ),
            cleanup_sandbox_fn=lambda _s: None,
            on_event=on_event,
        )
        assert events["trigger"]["errors"] == ["trigger failed"]
        assert events["agent"]["errors"] == ["missing CURSOR_API_KEY"]

    def test_on_event_unfixable_reason_included_once(self, sandbox: Path) -> None:
        events: dict[str, dict] = {}

        def on_event(name: str, payload: dict) -> None:
            events[name] = payload

        result = run_loop_iteration(
            loop=_loop(max_attempts=1),
            cwd=sandbox.parent,
            config=_config(),
            agent=_FakeAgent(
                [
                    AgentResponse(
                        status=AgentResponseStatus.UNFIXABLE,
                        duration_ms=1,
                        unfixable_reason="cannot fix",
                    )
                ]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.FAILED),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK,
                session=_session(sandbox),
            ),
            cleanup_sandbox_fn=lambda _s: None,
            on_event=on_event,
        )
        assert events["agent"]["errors"] == ["cannot fix"]
        assert result.attempts[0].errors.count("cannot fix") == 1

    def test_prompt_dump_writes_local_agent_input(
        self, sandbox: Path, tmp_path: Path
    ) -> None:
        dump_dir = tmp_path / "dumps"
        result, agent, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1, provider="local"),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)
            ],
            prompt_dump_dir=dump_dir,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert len(agent.requests) == 1
        dump_file = dump_dir / "wt-agent-prompt-sbx_test01-attempt-01.json"
        assert dump_file.exists()
        dumped = dump_file.read_text(encoding="utf-8")
        expected = json.dumps(
            agent.requests[0].model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
        assert dumped == expected + "\n"

    def test_prompt_dump_emits_event(self, sandbox: Path, tmp_path: Path) -> None:
        events: list[tuple[str, dict]] = []

        def on_event(name: str, payload: dict) -> None:
            events.append((name, payload))

        run_loop_iteration(
            loop=_loop(max_attempts=1, provider="local"),
            cwd=sandbox.parent,
            config=_config(),
            agent=_FakeAgent(
                [AgentResponse(status=AgentResponseStatus.NO_OP, duration_ms=1)]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.FAILED),
            apply_patch_fn=lambda **_k: PatchApplyResult(
                status=PatchApplyStatus.APPLIED
            ),
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK,
                session=_session(sandbox),
            ),
            cleanup_sandbox_fn=lambda _s: None,
            on_event=on_event,
            prompt_dump_dir=tmp_path / "dumps",
        )
        names = [name for name, _ in events]
        assert "agent_prompt_dumped" in names
        dump_payload = next(
            payload for name, payload in events if name == "agent_prompt_dumped"
        )
        assert dump_payload["provider"] == "local"
        assert dump_payload["path"].endswith(
            "wt-agent-prompt-sbx_test01-attempt-01.json"
        )

    def test_direct_mutation_validation_failure_discards(self, sandbox: Path) -> None:
        # Direct-mutation provider's diff fails the post-hoc validation gate
        # (too many touched files) -> runner must discard to baseline instead
        # of treating the mutation as applied.
        spy: dict[str, list] = {}
        many_files_diff = "".join(
            f"diff --git a/f{i}.py b/f{i}.py\n" for i in range(11)
        )
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff=many_files_diff,
                    mutation_baseline_ref="baseline-sha",
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.attempts[0].patch_status == "too_many_files"
        assert "patch_calls" not in spy
        assert spy["discard_calls"] == [(sandbox, "baseline-sha")]

    def test_abort_after_approval_before_patch_apply(self, sandbox: Path) -> None:
        # Abort observed right after approval is granted, before the patch is
        # applied: must stop as ABORTED without invoking the patch applier.
        event = threading.Event()

        def approve(_diff: str) -> bool:
            event.set()
            return True

        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2, require_before_apply=True),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                )
            ],
            approve_patch=approve,
            abort_event=event,
            spy=spy,
        )
        assert result.status == LoopFinalStatus.ABORTED
        assert result.stop_reason == "user_abort"
        assert len(result.attempts) == 1
        assert result.attempts[0].patch_status is None
        assert "patch_calls" not in spy

    def test_session_timeout_between_attempts(self, sandbox: Path) -> None:
        # Timeout tripped at the top of the loop, between attempts, once a
        # full attempt (fast trigger/agent, slow patch apply) has elapsed —
        # distinct from the mid-attempt check in
        # test_session_timeout_before_agent.
        def slow_patch(**_k: object) -> PatchApplyResult:
            time.sleep(1.05)
            return PatchApplyResult(status=PatchApplyStatus.APPLIED)

        result = run_loop_iteration(
            loop=_loop(max_attempts=3),
            cwd=sandbox.parent,
            config=_config(),
            agent=_FakeAgent(
                [
                    AgentResponse(
                        status=AgentResponseStatus.PROPOSED_PATCH,
                        unified_diff="diff --git a/a.py b/a.py\n",
                        duration_ms=1,
                    )
                ]
            ),
            list_changed_files=lambda _p: [],
            run_trigger_fn=lambda **_k: _trigger(TriggerRunStatus.FAILED),
            apply_patch_fn=slow_patch,
            build_payload_fn=lambda **_k: _payload(),
            create_sandbox_fn=lambda: SandboxCreateResult(
                status=SandboxCreateStatus.OK, session=_session(sandbox)
            ),
            cleanup_sandbox_fn=lambda _s: None,
            session_timeout_seconds=1,
            detect_repeat_failures=False,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.stop_reason == "session_timeout"
        # First attempt completes (patch applied); second attempt never
        # starts because the between-attempts timeout check trips first.
        assert len(result.attempts) == 1


class DirectMutationProviderTests:
    """Runner behavior for providers that set ``mutation_baseline_ref``."""

    def test_approved_skips_patch_applier(self, sandbox: Path) -> None:
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2),
            triggers=[
                _trigger(TriggerRunStatus.FAILED),
                _trigger(TriggerRunStatus.PASSED),
            ],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                    mutation_baseline_ref="baseline-sha",
                    duration_ms=3,
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.PASSED
        assert result.attempts[0].patch_status == "applied"
        assert result.attempts[0].patch_touched_files == ["a.py"]
        assert "patch_calls" not in spy
        assert "discard_calls" not in spy

    def test_rejected_discards_to_baseline(self, sandbox: Path) -> None:
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1, require_before_apply=True),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                    mutation_baseline_ref="baseline-sha",
                )
            ],
            approve_patch=lambda _diff: False,
            spy=spy,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert result.attempts[0].patch_status == "approval_rejected"
        assert "patch_calls" not in spy
        assert spy["discard_calls"] == [(sandbox, "baseline-sha")]

    def test_timeout_discards_to_baseline(self, sandbox: Path) -> None:
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.TIMEOUT,
                    mutation_baseline_ref="baseline-sha",
                    errors=["Agent timed out"],
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert spy["discard_calls"] == [(sandbox, "baseline-sha")]

    def test_unfixable_discards_to_baseline(self, sandbox: Path) -> None:
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.UNFIXABLE,
                    mutation_baseline_ref="baseline-sha",
                    unfixable_reason="cannot fix",
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.UNFIXABLE
        assert spy["discard_calls"] == [(sandbox, "baseline-sha")]

    def test_gate_failure_from_adapter_does_not_double_discard(
        self, sandbox: Path
    ) -> None:
        # Adapter-side gate failures already discarded and return
        # PROVIDER_ERROR without a baseline; runner must not call discard
        # again with no baseline available.
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=1),
            triggers=[_trigger(TriggerRunStatus.FAILED)],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROVIDER_ERROR,
                    errors=["gate violation"],
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.FAILED
        assert "discard_calls" not in spy

    def test_local_provider_response_unaffected(self, sandbox: Path) -> None:
        spy: dict[str, list] = {}
        result, _, _ = _run(
            sandbox=sandbox,
            loop=_loop(max_attempts=2),
            triggers=[
                _trigger(TriggerRunStatus.FAILED),
                _trigger(TriggerRunStatus.PASSED),
            ],
            agent_responses=[
                AgentResponse(
                    status=AgentResponseStatus.PROPOSED_PATCH,
                    unified_diff="diff --git a/a.py b/a.py\n",
                    duration_ms=3,
                )
            ],
            spy=spy,
        )
        assert result.status == LoopFinalStatus.PASSED
        assert len(spy["patch_calls"]) == 1
        assert "discard_calls" not in spy
