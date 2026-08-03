"""Iteration controller: sandbox → trigger → agent → patch until stop."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from getworktree.core.config.loader import load_config_result
from getworktree.core.config.models import WorktreeConfig
from getworktree.core.git_sandbox import (
    GitSandboxManager,
    SandboxCreateResult,
    SandboxSession,
    should_cleanup_sandbox,
)
from getworktree.core.loops.models import LoopDefinition
from getworktree.core.loops.patch import (
    PatchApplyResult,
    PatchApplyStatus,
    apply_patch_result,
)
from getworktree.core.loops.payload import AgentFailurePayload, build_failure_payload
from getworktree.core.loops.trigger import TriggerRunResult, run_trigger

if TYPE_CHECKING:
    from getworktree.core.agents.base import AgentAdapter

ApprovePatchFn = Callable[[str], bool]
ListChangedFilesFn = Callable[[Path], list[str]]
RunTriggerFn = Callable[..., TriggerRunResult]
ApplyPatchFn = Callable[..., PatchApplyResult]
BuildPayloadFn = Callable[..., AgentFailurePayload]
OnAttemptEndFn = Callable[["AttemptRecord"], None]
OnEventFn = Callable[[str, dict[str, Any]], None]
IsAbortedFn = Callable[[], bool]
CreateSandboxFn = Callable[[], SandboxCreateResult]
CleanupSandboxFn = Callable[[SandboxSession], None]


class LoopFinalStatus(StrEnum):
    """Terminal status for one loop run session."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    UNFIXABLE = "UNFIXABLE"
    ABORTED = "ABORTED"


class AttemptRecord(BaseModel):
    """One attempt within a loop run."""

    model_config = {"extra": "forbid", "strict": True}

    attempt: int
    trigger_status: str | None = None
    agent_status: str | None = None
    patch_status: str | None = None
    errors: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    trigger_exit_code: int | None = None
    trigger_duration_ms: int | None = None
    agent_duration_ms: int | None = None
    patch_touched_files: list[str] = Field(default_factory=list)
    trigger_stdout: str = ""
    trigger_stderr: str = ""


class LoopRunResult(BaseModel):
    """Structured outcome of ``run_loop_iteration``."""

    model_config = {"extra": "forbid", "strict": True}

    status: LoopFinalStatus
    session_id: str
    loop_name: str
    sandbox_path: Path | None = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    stop_reason: str
    errors: list[str] = Field(default_factory=list)
    max_attempts: int = 0
    sandbox_retained: bool = False

    @property
    def ok(self) -> bool:
        """Return True only when the loop finished with PASSED."""
        return self.status == LoopFinalStatus.PASSED


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _approval_callback_missing_error() -> str:
    return (
        "approval.require_before_apply is true but no approve_patch callback "
        "was provided (approval_callback_missing).\n"
        "Fix:\n"
        "- pass approve_patch=... to run_loop_iteration, or\n"
        "- set approval.require_before_apply false on the loop/config"
    )


def _configuration_error(detail: str) -> str:
    return f"Loop run configuration error: {detail}"


def resolve_max_attempts(
    *,
    loop: LoopDefinition,
    config: WorktreeConfig,
    caller_max_attempts: int | None = None,
) -> int:
    """Resolve effective max attempts with hard-limit clamp.

    Precedence:
    ``caller_max_attempts`` → ``loop.iteration.max_attempts`` →
    ``config.loop.default_max_attempts``, then
    ``min(..., config.loop.max_attempts_hard_limit)``.
    """
    if caller_max_attempts is not None:
        effective = caller_max_attempts
    else:
        effective = loop.iteration.max_attempts or config.loop.default_max_attempts
    return min(effective, config.loop.max_attempts_hard_limit)


def default_list_changed_files(sandbox_path: Path) -> list[str]:
    """List sandbox-relative paths changed vs HEAD via ``git diff --name-only``."""
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    lines = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines()]
    return sorted({line for line in lines if line})


def _is_aborted(
    *,
    abort_event: threading.Event | None,
    is_aborted: IsAbortedFn | None,
) -> bool:
    if abort_event is not None and abort_event.is_set():
        return True
    if is_aborted is not None and is_aborted():
        return True
    return False


def _emit(
    on_event: OnEventFn | None,
    name: str,
    **payload: Any,
) -> None:
    if on_event is not None:
        on_event(name, payload)


def _trigger_summary(result: TriggerRunResult) -> str:
    return result.status.value


def run_loop_iteration(
    *,
    loop: LoopDefinition,
    cwd: Path | None = None,
    config: WorktreeConfig | None = None,
    caller_max_attempts: int | None = None,
    auto_clean: bool | None = None,
    keep_on_failure: bool | None = None,
    require_before_apply: bool | None = None,
    abort_event: threading.Event | None = None,
    is_aborted: IsAbortedFn | None = None,
    approve_patch: ApprovePatchFn | None = None,
    agent: AgentAdapter | None = None,
    list_changed_files: ListChangedFilesFn | None = None,
    run_trigger_fn: RunTriggerFn | None = None,
    apply_patch_fn: ApplyPatchFn | None = None,
    build_payload_fn: BuildPayloadFn | None = None,
    create_sandbox_fn: CreateSandboxFn | None = None,
    cleanup_sandbox_fn: CleanupSandboxFn | None = None,
    on_attempt_end: OnAttemptEndFn | None = None,
    on_event: OnEventFn | None = None,
    session_id: str | None = None,
) -> LoopRunResult:
    """Run one full loop session attempt cycle.

    Orchestrates sandbox create → trigger → (on failure) payload → agent →
    optional approval → patch apply → next attempt until a terminal stop.

    Args:
        loop: Validated loop definition.
        cwd: Repository root. Defaults to process CWD.
        config: Effective config; loaded from ``cwd`` when omitted.
        caller_max_attempts: Optional CLI override for attempt budget.
        auto_clean: Override loop/config sandbox auto_clean when set.
        keep_on_failure: Override loop/config keep_on_failure when set.
        require_before_apply: Override approval gate when set.
        abort_event: Cooperative abort flag checked between steps.
        is_aborted: Alternate abort predicate.
        approve_patch: Approval callback when require_before_apply is true.
        agent: Injected agent adapter; defaults to factory from loop provider.
        list_changed_files: Callable returning sandbox-relative changed paths.
        run_trigger_fn: Injected trigger runner (tests).
        apply_patch_fn: Injected patch apply (tests).
        build_payload_fn: Injected payload builder (tests).
        create_sandbox_fn: Injected sandbox create (tests).
        cleanup_sandbox_fn: Injected sandbox cleanup (tests).
        on_attempt_end: Optional hook after each attempt record is finalized.
        on_event: Optional structured event callback for UX streaming.
        session_id: Optional fixed sandbox session id.

    Returns:
        Structured :class:`LoopRunResult` (never raises for classified paths).
    """
    # Lazy imports avoid circular dependency: agents.base → loops.payload → loops.
    from getworktree.core.agents.base import AgentRequest, AgentResponseStatus
    from getworktree.core.agents.factory import get_agent_adapter

    root = (cwd or Path.cwd()).expanduser().resolve()
    loop_name = loop.name
    empty_session = session_id or ""

    if config is None:
        load = load_config_result(cwd=root)
        if not load.ok or load.config is None:
            detail = load.errors[0] if load.errors else str(load.status)
            return LoopRunResult(
                status=LoopFinalStatus.FAILED,
                session_id=empty_session,
                loop_name=loop_name,
                stop_reason="configuration_error",
                errors=[_configuration_error(detail)],
            )
        config = load.config

    try:
        max_attempts = resolve_max_attempts(
            loop=loop,
            config=config,
            caller_max_attempts=caller_max_attempts,
        )
    except Exception as exc:  # defensive
        return LoopRunResult(
            status=LoopFinalStatus.FAILED,
            session_id=empty_session,
            loop_name=loop_name,
            stop_reason="configuration_error",
            errors=[_configuration_error(str(exc))],
        )

    if max_attempts < 1:
        return LoopRunResult(
            status=LoopFinalStatus.FAILED,
            session_id=empty_session,
            loop_name=loop_name,
            stop_reason="configuration_error",
            max_attempts=max_attempts,
            errors=[
                _configuration_error(
                    f"effective max_attempts is {max_attempts} (must be >= 1)"
                )
            ],
        )

    resolved_auto = auto_clean if auto_clean is not None else loop.sandbox.auto_clean
    resolved_keep = (
        keep_on_failure if keep_on_failure is not None else loop.sandbox.keep_on_failure
    )
    # Effective approval: explicit override, else loop definition, else config.
    if require_before_apply is not None:
        resolved_require = require_before_apply
    else:
        resolved_require = loop.approval.require_before_apply

    stop_when = set(loop.iteration.stop_when)
    trigger_runner = run_trigger_fn or run_trigger
    patch_applier = apply_patch_fn or apply_patch_result
    payload_builder = build_payload_fn or build_failure_payload
    changed_files_fn = list_changed_files or default_list_changed_files

    manager: GitSandboxManager | None = None
    session: SandboxSession | None = None

    if create_sandbox_fn is not None:
        create_result = create_sandbox_fn()
    else:
        manager = GitSandboxManager(cwd=root)
        create_result = manager.create_sandbox_result(session_id=session_id)

    if not create_result.ok or create_result.session is None:
        errors = list(create_result.errors) or [
            f"Sandbox create failed: {create_result.status}"
        ]
        return LoopRunResult(
            status=LoopFinalStatus.FAILED,
            session_id=session_id or "",
            loop_name=loop_name,
            stop_reason="sandbox_create_failed",
            max_attempts=max_attempts,
            errors=errors,
        )

    session = create_result.session
    sandbox_path = session.sandbox_path
    sid = session.session_id
    attempts: list[AttemptRecord] = []
    final_status = LoopFinalStatus.FAILED
    stop_reason = "max_attempts_exhausted"
    run_errors: list[str] = []
    command_passed: bool | None = None

    if agent is None:
        try:
            agent = get_agent_adapter(loop.agent.provider, config=config.agent)
        except ValueError as exc:
            run_errors.append(str(exc))
            final_status = LoopFinalStatus.FAILED
            stop_reason = "configuration_error"
            _finish_cleanup = True
        else:
            _finish_cleanup = False
    else:
        _finish_cleanup = False

    def _cleanup() -> None:
        nonlocal session
        if session is None:
            return
        session.command_passed = command_passed
        do_clean = should_cleanup_sandbox(
            auto_clean=resolved_auto,
            keep_on_failure=resolved_keep,
            command_passed=command_passed,
        )
        if not do_clean:
            return
        if cleanup_sandbox_fn is not None:
            cleanup_sandbox_fn(session)
        elif manager is not None:
            manager.cleanup_sandbox(session)

    if _finish_cleanup or agent is None:
        _cleanup()
        retained = not should_cleanup_sandbox(
            auto_clean=resolved_auto,
            keep_on_failure=resolved_keep,
            command_passed=command_passed,
        )
        return LoopRunResult(
            status=final_status,
            session_id=sid,
            loop_name=loop_name,
            sandbox_path=sandbox_path if retained else None,
            attempts=attempts,
            stop_reason=stop_reason,
            errors=run_errors,
            max_attempts=max_attempts,
            sandbox_retained=retained,
        )

    reject_binary = (
        loop.patch.reject_binary_changes
        if loop.patch.reject_binary_changes is not None
        else config.patch.reject_binary_changes
    )
    max_files = loop.patch.max_files
    max_patch_kb = loop.patch.max_patch_kb

    try:
        for attempt_idx in range(1, max_attempts + 1):
            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            record = AttemptRecord(attempt=attempt_idx, started_at=_now_iso())
            _emit(
                on_event,
                "attempt_start",
                attempt=attempt_idx,
                max_attempts=max_attempts,
            )

            # --- trigger ---
            trigger_result = trigger_runner(
                command=loop.trigger.command,
                args=list(loop.trigger.args),
                cwd=sandbox_path,
                timeout_seconds=loop.trigger.timeout_seconds,
            )
            record.trigger_status = _trigger_summary(trigger_result)
            record.trigger_exit_code = trigger_result.exit_code
            record.trigger_duration_ms = trigger_result.duration_ms
            record.trigger_stdout = trigger_result.stdout
            record.trigger_stderr = trigger_result.stderr
            if trigger_result.errors:
                record.errors.extend(trigger_result.errors)

            _emit(
                on_event,
                "trigger",
                attempt=attempt_idx,
                status=record.trigger_status,
                exit_code=trigger_result.exit_code,
                duration_ms=trigger_result.duration_ms,
            )

            if trigger_result.ok:
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                # Trigger pass is always terminal success (FR-1 / FR-4).
                final_status = LoopFinalStatus.PASSED
                stop_reason = "trigger_passed"
                command_passed = True
                break

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            # --- payload + agent ---
            changed = changed_files_fn(sandbox_path)
            payload = payload_builder(
                trigger=trigger_result,
                sandbox_path=sandbox_path,
                include=list(loop.context.include),
                changed_files=changed,
            )
            agent_request = AgentRequest(
                mode=loop.agent.mode,
                payload=payload,
                sandbox_path=sandbox_path,
                timeout_seconds=loop.agent.timeout_seconds,
                model=config.agent.model,
                endpoint=config.agent.endpoint,
                temperature=config.agent.temperature,
                max_tokens=config.agent.max_tokens,
            )
            agent_response = agent.propose_fix(agent_request)
            record.agent_status = agent_response.status.value
            record.agent_duration_ms = agent_response.duration_ms
            if agent_response.errors:
                record.errors.extend(agent_response.errors)

            _emit(
                on_event,
                "agent",
                attempt=attempt_idx,
                status=record.agent_status,
                duration_ms=agent_response.duration_ms,
            )

            if agent_response.status == AgentResponseStatus.UNFIXABLE:
                if agent_response.unfixable_reason:
                    record.errors.append(agent_response.unfixable_reason)
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                if "unfixable" in stop_when:
                    final_status = LoopFinalStatus.UNFIXABLE
                    stop_reason = "agent_unfixable"
                    command_passed = False
                    break
                if attempt_idx >= max_attempts:
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "max_attempts_exhausted"
                    command_passed = False
                    break
                continue

            if agent_response.status in {
                AgentResponseStatus.TIMEOUT,
                AgentResponseStatus.PROVIDER_ERROR,
                AgentResponseStatus.NO_OP,
            }:
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                    final_status = LoopFinalStatus.ABORTED
                    stop_reason = "user_abort"
                    break
                if attempt_idx >= max_attempts:
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "max_attempts_exhausted"
                    command_passed = False
                    break
                continue

            # proposed_patch
            if not agent_response.unified_diff:
                record.errors.append("Agent proposed_patch without unified_diff")
                record.patch_status = PatchApplyStatus.EMPTY_DIFF.value
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                if attempt_idx >= max_attempts:
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "max_attempts_exhausted"
                    command_passed = False
                    break
                continue

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            # --- approval ---
            if resolved_require:
                if approve_patch is None:
                    record.errors.append(_approval_callback_missing_error())
                    record.patch_status = "approval_callback_missing"
                    record.finished_at = _now_iso()
                    attempts.append(record)
                    if on_attempt_end is not None:
                        on_attempt_end(record)
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "configuration_error"
                    run_errors.append(_approval_callback_missing_error())
                    command_passed = False
                    break
                approved = bool(approve_patch(agent_response.unified_diff))
                if not approved:
                    record.patch_status = "approval_rejected"
                    record.errors.append("Patch apply skipped: approval rejected")
                    record.finished_at = _now_iso()
                    attempts.append(record)
                    if on_attempt_end is not None:
                        on_attempt_end(record)
                    _emit(
                        on_event,
                        "patch",
                        attempt=attempt_idx,
                        status="approval_rejected",
                    )
                    if attempt_idx >= max_attempts:
                        final_status = LoopFinalStatus.FAILED
                        stop_reason = "max_attempts_exhausted"
                        command_passed = False
                        break
                    continue

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                record.finished_at = _now_iso()
                attempts.append(record)
                if on_attempt_end is not None:
                    on_attempt_end(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            patch_result = patch_applier(
                sandbox_path=sandbox_path,
                unified_diff=agent_response.unified_diff,
                max_files=max_files,
                max_patch_kb=max_patch_kb,
                reject_binary_changes=reject_binary,
                check_only=False,
            )
            record.patch_status = patch_result.status.value
            record.patch_touched_files = list(patch_result.touched_files)
            if patch_result.errors:
                record.errors.extend(patch_result.errors)

            _emit(
                on_event,
                "patch",
                attempt=attempt_idx,
                status=record.patch_status,
                touched_files=list(patch_result.touched_files),
            )

            record.finished_at = _now_iso()
            attempts.append(record)
            if on_attempt_end is not None:
                on_attempt_end(record)

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            if not patch_result.ok:
                if attempt_idx >= max_attempts:
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "max_attempts_exhausted"
                    command_passed = False
                    break
                continue

            # Patch applied — continue to next attempt (re-trigger).
            if attempt_idx >= max_attempts:
                # No attempts left to re-trigger after final apply.
                final_status = LoopFinalStatus.FAILED
                stop_reason = "max_attempts_exhausted"
                command_passed = False
                break
            continue
        else:
            # for-loop exhausted without break
            if final_status != LoopFinalStatus.PASSED:
                final_status = LoopFinalStatus.FAILED
                stop_reason = "max_attempts_exhausted"
                command_passed = False

    finally:
        if command_passed is None and final_status == LoopFinalStatus.PASSED:
            command_passed = True
        elif command_passed is None and final_status in {
            LoopFinalStatus.FAILED,
            LoopFinalStatus.UNFIXABLE,
        }:
            command_passed = False
        # ABORTED leaves command_passed as None (unclassified) per sandbox policy.

        session.command_passed = command_passed
        will_clean = should_cleanup_sandbox(
            auto_clean=resolved_auto,
            keep_on_failure=resolved_keep,
            command_passed=command_passed,
        )
        if will_clean:
            if cleanup_sandbox_fn is not None:
                cleanup_sandbox_fn(session)
            elif manager is not None:
                manager.cleanup_sandbox(session)
            retained = False
            result_sandbox: Path | None = None
        else:
            retained = True
            result_sandbox = sandbox_path

    return LoopRunResult(
        status=final_status,
        session_id=sid,
        loop_name=loop_name,
        sandbox_path=result_sandbox,
        attempts=attempts,
        stop_reason=stop_reason,
        errors=run_errors,
        max_attempts=max_attempts,
        sandbox_retained=retained,
    )
