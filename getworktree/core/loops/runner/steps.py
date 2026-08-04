"""Per-attempt step functions dispatched by ``run_loop_iteration``.

``_LoopContext`` bundles the resolved, per-run configuration and injectable
callbacks shared by every attempt; it is stateful (not a schema), so it lives
here rather than in ``runner_models.py``. Each ``_run_*_step`` function reads
from and appends to a shared ``_LoopContext`` plus the per-attempt
``AttemptRecord`` it's given, returning a ``StepOutcome`` (or ``None`` to
proceed to the next step) for the orchestrator in ``runner.py`` to dispatch
on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from getworktree.core.config.models import WorktreeConfig
from getworktree.core.loops.models import LoopDefinition
from getworktree.core.loops.patch import (
    PatchApplyResult,
    PatchApplyStatus,
    validate_patch_text,
)
from getworktree.core.loops.runner.helpers import (
    _advance_or_exhaust,
    _dump_agent_input,
    _emit,
    _is_aborted,
    _now_iso,
    _trigger_summary,
)
from getworktree.core.loops.runner_models import (
    ApplyPatchFn,
    ApprovePatchFn,
    AttemptRecord,
    BuildPayloadFn,
    DiscardMutationFn,
    IsAbortedFn,
    ListChangedFilesFn,
    LoopFinalStatus,
    OnAttemptEndFn,
    OnEventFn,
    RunTriggerFn,
    StepOutcome,
    StopReason,
)
from getworktree.core.loops.safety import (
    SafetyState,
    failure_signature,
    record_agent_status,
    record_trigger_failure,
    record_trigger_success,
    session_timed_out,
)
from getworktree.core.loops.trigger import TriggerRunResult

if TYPE_CHECKING:
    from getworktree.core.agents.base import AgentAdapter, AgentResponse


@dataclass
class _LoopContext:
    """Resolved, per-run state shared by every attempt step.

    Built once by ``run_loop_iteration`` after config/sandbox/agent
    resolution. Step functions read from and append to this object plus the
    per-attempt ``AttemptRecord`` they're given, so the attempt loop itself
    only has to dispatch on the ``StepOutcome`` each step returns.
    """

    loop: LoopDefinition
    config: WorktreeConfig
    agent: AgentAdapter
    sandbox_path: Path
    session_id: str
    max_attempts: int
    stop_when: set[str]
    resolved_require: bool
    reject_binary: bool
    max_files: int | None
    max_patch_kb: int | None
    resolved_detect_repeat: bool
    resolved_session_timeout: int | None
    trigger_runner: RunTriggerFn
    patch_applier: ApplyPatchFn
    mutation_discarder: DiscardMutationFn
    payload_builder: BuildPayloadFn
    changed_files_fn: ListChangedFilesFn
    approve_patch: ApprovePatchFn | None
    abort_event: threading.Event | None
    is_aborted: IsAbortedFn | None
    on_event: OnEventFn | None
    on_attempt_end: OnAttemptEndFn | None
    prompt_dump_dir: Path | None
    attempts: list[AttemptRecord]
    run_errors: list[str]
    safety: SafetyState = field(default_factory=SafetyState)

    def aborted(self) -> bool:
        """Return True when a cooperative abort has been requested."""
        return _is_aborted(abort_event=self.abort_event, is_aborted=self.is_aborted)

    def timed_out(self) -> bool:
        """Return True when the session wall-clock cap has been exceeded."""
        return session_timed_out(
            self.safety, session_timeout_seconds=self.resolved_session_timeout
        )

    def finish_attempt(self, record: AttemptRecord) -> None:
        """Stamp ``record`` as finished, append it, and fire the hook."""
        record.finished_at = _now_iso()
        self.attempts.append(record)
        if self.on_attempt_end is not None:
            self.on_attempt_end(record)


def _run_trigger_step(
    ctx: _LoopContext, attempt_idx: int, record: AttemptRecord
) -> tuple[StepOutcome | None, TriggerRunResult | None]:
    """Run the trigger command and classify its result.

    Returns:
        A ``(outcome, trigger_result)`` pair. ``outcome`` is ``None`` and
        ``trigger_result`` is populated to proceed to the agent step;
        otherwise ``outcome`` is a terminal ``StepOutcome`` (trigger passed,
        a repeat-failure stop condition tripped, or an abort/timeout was
        observed after the trigger ran) and ``trigger_result`` is ``None``.
    """
    _emit(
        ctx.on_event,
        "trigger_start",
        attempt=attempt_idx,
        command=ctx.loop.trigger.command,
        args=list(ctx.loop.trigger.args),
        timeout_seconds=ctx.loop.trigger.timeout_seconds,
    )
    trigger_result = ctx.trigger_runner(
        command=ctx.loop.trigger.command,
        args=list(ctx.loop.trigger.args),
        cwd=ctx.sandbox_path,
        timeout_seconds=ctx.loop.trigger.timeout_seconds,
    )
    record.trigger_status = _trigger_summary(trigger_result)
    record.trigger_exit_code = trigger_result.exit_code
    record.trigger_duration_ms = trigger_result.duration_ms
    record.trigger_stdout = trigger_result.stdout
    record.trigger_stderr = trigger_result.stderr
    if trigger_result.errors:
        record.errors.extend(trigger_result.errors)

    _emit(
        ctx.on_event,
        "trigger",
        attempt=attempt_idx,
        status=record.trigger_status,
        exit_code=trigger_result.exit_code,
        duration_ms=trigger_result.duration_ms,
        errors=list(trigger_result.errors),
    )

    if trigger_result.ok:
        record_trigger_success(ctx.safety)
        ctx.finish_attempt(record)
        # Trigger pass is always terminal success (FR-1 / FR-4).
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.PASSED,
                stop_reason=StopReason.TRIGGER_PASSED,
                command_passed=True,
            ),
            None,
        )

    sig = failure_signature(
        record.trigger_status or "failed",
        trigger_result.exit_code,
        trigger_result.stdout,
        trigger_result.stderr,
    )
    repeat_stop = record_trigger_failure(
        ctx.safety,
        signature=sig,
        detect_repeat_failures=ctx.resolved_detect_repeat,
    )
    if repeat_stop is not None:
        ctx.finish_attempt(record)
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.FAILED,
                stop_reason=StopReason(repeat_stop),
                command_passed=False,
            ),
            None,
        )

    if ctx.aborted():
        ctx.finish_attempt(record)
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.ABORTED,
                stop_reason=StopReason.USER_ABORT,
            ),
            None,
        )

    if ctx.timed_out():
        ctx.finish_attempt(record)
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.FAILED,
                stop_reason=StopReason.SESSION_TIMEOUT,
                command_passed=False,
            ),
            None,
        )

    return (None, trigger_result)


def _run_agent_step(
    ctx: _LoopContext,
    attempt_idx: int,
    record: AttemptRecord,
    *,
    trigger_result: TriggerRunResult,
) -> tuple[StepOutcome | None, AgentResponse | None]:
    """Build the failure payload, call the agent, and classify its response.

    Returns:
        A ``(outcome, agent_response)`` pair. ``outcome`` is ``None`` to
        proceed to the approval step (agent proposed a usable patch);
        otherwise it's a terminal-or-retry ``StepOutcome`` and
        ``agent_response`` is ``None``.
    """
    # Lazy import avoids circular dependency: agents.base → loops.payload → loops.
    from getworktree.core.agents.base import AgentRequest, AgentResponseStatus

    changed = ctx.changed_files_fn(ctx.sandbox_path)
    payload = ctx.payload_builder(
        trigger=trigger_result,
        sandbox_path=ctx.sandbox_path,
        include=list(ctx.loop.context.include),
        changed_files=changed,
    )
    agent_request = AgentRequest(
        mode=ctx.loop.agent.mode,
        payload=payload,
        sandbox_path=ctx.sandbox_path,
        timeout_seconds=ctx.loop.agent.timeout_seconds,
        model=ctx.config.agent.model,
        endpoint=ctx.config.agent.endpoint,
        temperature=ctx.config.agent.temperature,
        max_tokens=ctx.config.agent.max_tokens,
        max_files=ctx.max_files,
        max_patch_kb=ctx.max_patch_kb,
        reject_binary_changes=ctx.reject_binary,
    )
    if ctx.prompt_dump_dir is not None:
        dumped_path, dump_error = _dump_agent_input(
            provider=ctx.loop.agent.provider,
            request=agent_request,
            dump_dir=ctx.prompt_dump_dir,
            session_id=ctx.session_id,
            attempt=attempt_idx,
        )
        if dumped_path is not None:
            _emit(
                ctx.on_event,
                "agent_prompt_dumped",
                attempt=attempt_idx,
                provider=ctx.loop.agent.provider,
                path=dumped_path.as_posix(),
            )
        if dump_error is not None:
            record.errors.append(dump_error)
            _emit(
                ctx.on_event,
                "agent_prompt_dump_error",
                attempt=attempt_idx,
                provider=ctx.loop.agent.provider,
                errors=[dump_error],
            )
    _emit(
        ctx.on_event,
        "agent_start",
        attempt=attempt_idx,
        provider=ctx.loop.agent.provider,
        mode=ctx.loop.agent.mode,
        timeout_seconds=ctx.loop.agent.timeout_seconds,
    )
    agent_response = ctx.agent.propose_fix(agent_request)
    record.agent_status = agent_response.status.value
    record.agent_duration_ms = agent_response.duration_ms
    agent_errors = list(agent_response.errors)
    if (
        agent_response.status == AgentResponseStatus.UNFIXABLE
        and agent_response.unfixable_reason
    ):
        agent_errors.append(agent_response.unfixable_reason)
    if agent_errors:
        record.errors.extend(agent_errors)

    _emit(
        ctx.on_event,
        "agent",
        attempt=attempt_idx,
        status=record.agent_status,
        duration_ms=agent_response.duration_ms,
        errors=agent_errors,
    )

    no_op_stop = record_agent_status(ctx.safety, agent_response.status.value)

    if agent_response.status == AgentResponseStatus.UNFIXABLE:
        if agent_response.mutation_baseline_ref is not None:
            ctx.mutation_discarder(
                ctx.sandbox_path, agent_response.mutation_baseline_ref
            )
        ctx.finish_attempt(record)
        if "unfixable" in ctx.stop_when:
            return (
                StepOutcome(
                    continue_loop=False,
                    final_status=LoopFinalStatus.UNFIXABLE,
                    stop_reason=StopReason.AGENT_UNFIXABLE,
                    command_passed=False,
                ),
                None,
            )
        return (_advance_or_exhaust(attempt_idx, ctx.max_attempts), None)

    if no_op_stop is not None:
        ctx.finish_attempt(record)
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.FAILED,
                stop_reason=StopReason(no_op_stop),
                command_passed=False,
            ),
            None,
        )

    if agent_response.status in {
        AgentResponseStatus.TIMEOUT,
        AgentResponseStatus.PROVIDER_ERROR,
        AgentResponseStatus.NO_OP,
    }:
        if agent_response.mutation_baseline_ref is not None:
            ctx.mutation_discarder(
                ctx.sandbox_path, agent_response.mutation_baseline_ref
            )
        ctx.finish_attempt(record)
        if ctx.aborted():
            return (
                StepOutcome(
                    continue_loop=False,
                    final_status=LoopFinalStatus.ABORTED,
                    stop_reason=StopReason.USER_ABORT,
                ),
                None,
            )
        return (_advance_or_exhaust(attempt_idx, ctx.max_attempts), None)

    # proposed_patch
    if not agent_response.unified_diff:
        record.errors.append("Agent proposed_patch without unified_diff")
        record.patch_status = PatchApplyStatus.EMPTY_DIFF.value
        if agent_response.mutation_baseline_ref is not None:
            ctx.mutation_discarder(
                ctx.sandbox_path, agent_response.mutation_baseline_ref
            )
        ctx.finish_attempt(record)
        return (_advance_or_exhaust(attempt_idx, ctx.max_attempts), None)

    if ctx.aborted():
        ctx.finish_attempt(record)
        return (
            StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.ABORTED,
                stop_reason=StopReason.USER_ABORT,
            ),
            None,
        )

    return (None, agent_response)


def _run_approval_step(
    ctx: _LoopContext,
    attempt_idx: int,
    record: AttemptRecord,
    agent_response: AgentResponse,
) -> StepOutcome | None:
    """Gate the proposed patch behind approval when configured.

    Returns:
        ``None`` to proceed to the patch step (no approval required, or
        approval granted and no abort observed); otherwise a
        terminal-or-retry ``StepOutcome``.
    """
    if ctx.resolved_require:
        if ctx.approve_patch is None:
            missing = (
                "approval.require_before_apply is true but no approve_patch "
                "callback was provided (approval_callback_missing).\n"
                "Fix:\n"
                "- pass approve_patch=... to run_loop_iteration, or\n"
                "- set approval.require_before_apply false on the loop/config"
            )
            record.errors.append(missing)
            record.patch_status = "approval_callback_missing"
            ctx.finish_attempt(record)
            ctx.run_errors.append(missing)
            return StepOutcome(
                continue_loop=False,
                final_status=LoopFinalStatus.FAILED,
                stop_reason=StopReason.CONFIGURATION_ERROR,
                command_passed=False,
            )
        approved = bool(ctx.approve_patch(agent_response.unified_diff))
        if not approved:
            record.patch_status = "approval_rejected"
            rejection_error = "Patch apply skipped: approval rejected"
            record.errors.append(rejection_error)
            if agent_response.mutation_baseline_ref is not None:
                ctx.mutation_discarder(
                    ctx.sandbox_path, agent_response.mutation_baseline_ref
                )
            ctx.finish_attempt(record)
            _emit(
                ctx.on_event,
                "patch",
                attempt=attempt_idx,
                status="approval_rejected",
                errors=[rejection_error],
            )
            return _advance_or_exhaust(attempt_idx, ctx.max_attempts)

    if ctx.aborted():
        ctx.finish_attempt(record)
        return StepOutcome(
            continue_loop=False,
            final_status=LoopFinalStatus.ABORTED,
            stop_reason=StopReason.USER_ABORT,
        )

    return None


def _run_patch_step(
    ctx: _LoopContext,
    attempt_idx: int,
    record: AttemptRecord,
    agent_response: AgentResponse,
) -> StepOutcome:
    """Apply (or check) the proposed patch and decide the next attempt.

    Always terminates the current attempt: returns ``continue_loop=True`` to
    retry (re-trigger) or a terminal ``StepOutcome`` to break.
    """
    _emit(
        ctx.on_event,
        "patch_start",
        attempt=attempt_idx,
    )
    if agent_response.mutation_baseline_ref is not None:
        # Direct-mutation provider: the agent already edited files on disk.
        # Do not re-`git apply` (it would conflict); the captured diff
        # already passed the adapter's post-hoc gate, so re-derive touched
        # files from the same pure check.
        validation = validate_patch_text(
            agent_response.unified_diff,
            max_files=ctx.max_files,
            max_patch_kb=ctx.max_patch_kb,
            reject_binary_changes=ctx.reject_binary,
            sandbox_path=ctx.sandbox_path,
        )
        if validation.status == PatchApplyStatus.CHECKED_OK:
            patch_result = PatchApplyResult(
                status=PatchApplyStatus.APPLIED,
                touched_files=list(validation.touched_files),
            )
        else:
            ctx.mutation_discarder(
                ctx.sandbox_path, agent_response.mutation_baseline_ref
            )
            patch_result = validation
    else:
        patch_result = ctx.patch_applier(
            sandbox_path=ctx.sandbox_path,
            unified_diff=agent_response.unified_diff,
            max_files=ctx.max_files,
            max_patch_kb=ctx.max_patch_kb,
            reject_binary_changes=ctx.reject_binary,
            check_only=False,
        )
    record.patch_status = patch_result.status.value
    record.patch_touched_files = list(patch_result.touched_files)
    if patch_result.errors:
        record.errors.extend(patch_result.errors)

    _emit(
        ctx.on_event,
        "patch",
        attempt=attempt_idx,
        status=record.patch_status,
        touched_files=list(patch_result.touched_files),
        errors=list(patch_result.errors),
    )

    ctx.finish_attempt(record)

    if ctx.aborted():
        return StepOutcome(
            continue_loop=False,
            final_status=LoopFinalStatus.ABORTED,
            stop_reason=StopReason.USER_ABORT,
        )

    if not patch_result.ok:
        return _advance_or_exhaust(attempt_idx, ctx.max_attempts)

    # Patch applied — continue to next attempt (re-trigger), unless this was
    # the last available attempt.
    return _advance_or_exhaust(attempt_idx, ctx.max_attempts)
