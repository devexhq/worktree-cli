"""Iteration controller: sandbox → trigger → agent → patch until stop."""

from __future__ import annotations

import json
import os
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
    validate_patch_text,
)
from getworktree.core.loops.payload import AgentFailurePayload, build_failure_payload
from getworktree.core.loops.safety import (
    SafetyState,
    failure_signature,
    record_agent_status,
    record_trigger_failure,
    record_trigger_success,
    session_timed_out,
)
from getworktree.core.loops.trigger import TriggerRunResult, run_trigger

if TYPE_CHECKING:
    from getworktree.core.agents.base import AgentAdapter

ApprovePatchFn = Callable[[str], bool]
ListChangedFilesFn = Callable[[Path], list[str]]
RunTriggerFn = Callable[..., TriggerRunResult]
ApplyPatchFn = Callable[..., PatchApplyResult]
DiscardMutationFn = Callable[[Path, str], None]
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


def _render_agent_input_dump(*, provider: str, request: Any) -> tuple[str, str]:
    """Return ``(suffix, content)`` for a provider-specific agent-input dump."""
    if provider in {"cursor", "gemini", "copilot"}:
        from getworktree.core.agents.cli_mutation import build_mutation_prompt

        return ("txt", build_mutation_prompt(request))
    if provider == "local":
        payload = request.model_dump(mode="json")
        return ("json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if provider == "ollama":
        from getworktree.core.agents.ollama import (
            DEFAULT_MAX_TOKENS,
            DEFAULT_TEMPERATURE,
            build_ollama_messages,
            resolve_ollama_endpoint,
        )

        body_obj = {
            "model": request.model or "",
            "stream": False,
            "messages": build_ollama_messages(request),
            "options": {
                "temperature": (
                    float(request.temperature)
                    if request.temperature is not None
                    else DEFAULT_TEMPERATURE
                ),
                "num_predict": (
                    int(request.max_tokens)
                    if request.max_tokens is not None
                    else DEFAULT_MAX_TOKENS
                ),
            },
            "endpoint": resolve_ollama_endpoint(request.endpoint),
        }
        return ("json", json.dumps(body_obj, indent=2, ensure_ascii=False) + "\n")
    payload = request.model_dump(mode="json")
    return ("json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _dump_agent_input(
    *,
    provider: str,
    request: Any,
    dump_dir: Path,
    session_id: str,
    attempt: int,
) -> tuple[Path | None, str | None]:
    """Write one provider-specific agent-input dump file.

    Returns:
        Tuple of ``(path, error)`` where exactly one item is non-None.
    """
    suffix, content = _render_agent_input_dump(provider=provider, request=request)
    dump_root = dump_dir.expanduser().resolve()
    filename = f"wt-agent-prompt-{session_id}-attempt-{attempt:02d}.{suffix}"
    output_path = dump_root / filename

    try:
        dump_root.mkdir(parents=True, exist_ok=True)
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        return (
            None,
            f"Failed to write agent input dump '{output_path}': {exc}",
        )

    return (output_path, None)


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
    discard_mutation_fn: DiscardMutationFn | None = None,
    build_payload_fn: BuildPayloadFn | None = None,
    create_sandbox_fn: CreateSandboxFn | None = None,
    cleanup_sandbox_fn: CleanupSandboxFn | None = None,
    on_attempt_end: OnAttemptEndFn | None = None,
    on_event: OnEventFn | None = None,
    session_id: str | None = None,
    session_timeout_seconds: int | None = None,
    detect_repeat_failures: bool | None = None,
    include_wip: bool = False,
    prompt_dump_dir: Path | None = None,
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
        discard_mutation_fn: Injected sandbox reset for direct-mutation
            providers (tests); defaults to ``discard_since``.
        build_payload_fn: Injected payload builder (tests).
        create_sandbox_fn: Injected sandbox create (tests).
        cleanup_sandbox_fn: Injected sandbox cleanup (tests).
        on_attempt_end: Optional hook after each attempt record is finalized.
        on_event: Optional structured event callback for UX streaming.
        session_id: Optional fixed sandbox session id.
        session_timeout_seconds: Session wall-clock cap; defaults to
            ``config.sandbox.default_timeout_seconds``.
        detect_repeat_failures: Override config ``loop.detect_repeat_failures``.
        include_wip: When True, overlay uncommitted working-tree changes into
            the sandbox after create (``--wip``).
        prompt_dump_dir: Optional directory to write provider-specific
            agent-input dumps (one file per attempt) before each agent call.

    Returns:
        Structured :class:`LoopRunResult` (never raises for classified paths).
    """
    # Lazy imports avoid circular dependency: agents.base → loops.payload → loops.
    from getworktree.core.agents.base import AgentRequest, AgentResponseStatus
    from getworktree.core.agents.factory import get_agent_adapter
    from getworktree.core.agents.mutation_git import discard_since

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
    mutation_discarder = discard_mutation_fn or discard_since
    payload_builder = build_payload_fn or build_failure_payload
    changed_files_fn = list_changed_files or default_list_changed_files

    manager: GitSandboxManager | None = None
    session: SandboxSession | None = None

    if create_sandbox_fn is not None:
        create_result = create_sandbox_fn()
    else:
        manager = GitSandboxManager(cwd=root)
        create_result = manager.create_sandbox_result(
            session_id=session_id,
            include_wip=include_wip,
        )

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

    _emit(
        on_event,
        "session_start",
        session_id=sid,
        sandbox_path=str(sandbox_path),
        loop_name=loop_name,
        max_attempts=max_attempts,
        wip=session.wip_applied,
        wip_paths=list(session.wip_paths),
    )

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

    resolved_session_timeout = (
        session_timeout_seconds
        if session_timeout_seconds is not None
        else config.sandbox.default_timeout_seconds
    )
    resolved_detect_repeat = (
        detect_repeat_failures
        if detect_repeat_failures is not None
        else config.loop.detect_repeat_failures
    )
    safety = SafetyState()

    def _finish_attempt(rec: AttemptRecord) -> None:
        rec.finished_at = _now_iso()
        attempts.append(rec)
        if on_attempt_end is not None:
            on_attempt_end(rec)

    try:
        for attempt_idx in range(1, max_attempts + 1):
            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            if session_timed_out(
                safety, session_timeout_seconds=resolved_session_timeout
            ):
                final_status = LoopFinalStatus.FAILED
                stop_reason = "session_timeout"
                command_passed = False
                break

            record = AttemptRecord(attempt=attempt_idx, started_at=_now_iso())
            _emit(
                on_event,
                "attempt_start",
                attempt=attempt_idx,
                max_attempts=max_attempts,
            )

            # --- trigger ---
            _emit(
                on_event,
                "trigger_start",
                attempt=attempt_idx,
                command=loop.trigger.command,
                args=list(loop.trigger.args),
                timeout_seconds=loop.trigger.timeout_seconds,
            )
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
                errors=list(trigger_result.errors),
            )

            if trigger_result.ok:
                record_trigger_success(safety)
                _finish_attempt(record)
                # Trigger pass is always terminal success (FR-1 / FR-4).
                final_status = LoopFinalStatus.PASSED
                stop_reason = "trigger_passed"
                command_passed = True
                break

            sig = failure_signature(
                record.trigger_status or "failed",
                trigger_result.exit_code,
                trigger_result.stdout,
                trigger_result.stderr,
            )
            repeat_stop = record_trigger_failure(
                safety,
                signature=sig,
                detect_repeat_failures=resolved_detect_repeat,
            )
            if repeat_stop is not None:
                _finish_attempt(record)
                final_status = LoopFinalStatus.FAILED
                stop_reason = repeat_stop
                command_passed = False
                break

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                _finish_attempt(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            if session_timed_out(
                safety, session_timeout_seconds=resolved_session_timeout
            ):
                _finish_attempt(record)
                final_status = LoopFinalStatus.FAILED
                stop_reason = "session_timeout"
                command_passed = False
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
                max_files=max_files,
                max_patch_kb=max_patch_kb,
                reject_binary_changes=reject_binary,
            )
            if prompt_dump_dir is not None:
                dumped_path, dump_error = _dump_agent_input(
                    provider=loop.agent.provider,
                    request=agent_request,
                    dump_dir=prompt_dump_dir,
                    session_id=sid,
                    attempt=attempt_idx,
                )
                if dumped_path is not None:
                    _emit(
                        on_event,
                        "agent_prompt_dumped",
                        attempt=attempt_idx,
                        provider=loop.agent.provider,
                        path=dumped_path.as_posix(),
                    )
                if dump_error is not None:
                    record.errors.append(dump_error)
                    _emit(
                        on_event,
                        "agent_prompt_dump_error",
                        attempt=attempt_idx,
                        provider=loop.agent.provider,
                        errors=[dump_error],
                    )
            _emit(
                on_event,
                "agent_start",
                attempt=attempt_idx,
                provider=loop.agent.provider,
                mode=loop.agent.mode,
                timeout_seconds=loop.agent.timeout_seconds,
            )
            agent_response = agent.propose_fix(agent_request)
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
                on_event,
                "agent",
                attempt=attempt_idx,
                status=record.agent_status,
                duration_ms=agent_response.duration_ms,
                errors=agent_errors,
            )

            no_op_stop = record_agent_status(safety, agent_response.status.value)

            if agent_response.status == AgentResponseStatus.UNFIXABLE:
                if agent_response.mutation_baseline_ref is not None:
                    mutation_discarder(
                        sandbox_path, agent_response.mutation_baseline_ref
                    )
                _finish_attempt(record)
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

            if no_op_stop is not None:
                _finish_attempt(record)
                final_status = LoopFinalStatus.FAILED
                stop_reason = no_op_stop
                command_passed = False
                break

            if agent_response.status in {
                AgentResponseStatus.TIMEOUT,
                AgentResponseStatus.PROVIDER_ERROR,
                AgentResponseStatus.NO_OP,
            }:
                if agent_response.mutation_baseline_ref is not None:
                    mutation_discarder(
                        sandbox_path, agent_response.mutation_baseline_ref
                    )
                _finish_attempt(record)
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
                if agent_response.mutation_baseline_ref is not None:
                    mutation_discarder(
                        sandbox_path, agent_response.mutation_baseline_ref
                    )
                _finish_attempt(record)
                if attempt_idx >= max_attempts:
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "max_attempts_exhausted"
                    command_passed = False
                    break
                continue

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                _finish_attempt(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            # --- approval ---
            if resolved_require:
                if approve_patch is None:
                    record.errors.append(_approval_callback_missing_error())
                    record.patch_status = "approval_callback_missing"
                    _finish_attempt(record)
                    final_status = LoopFinalStatus.FAILED
                    stop_reason = "configuration_error"
                    run_errors.append(_approval_callback_missing_error())
                    command_passed = False
                    break
                approved = bool(approve_patch(agent_response.unified_diff))
                if not approved:
                    record.patch_status = "approval_rejected"
                    rejection_error = "Patch apply skipped: approval rejected"
                    record.errors.append(rejection_error)
                    if agent_response.mutation_baseline_ref is not None:
                        mutation_discarder(
                            sandbox_path, agent_response.mutation_baseline_ref
                        )
                    _finish_attempt(record)
                    _emit(
                        on_event,
                        "patch",
                        attempt=attempt_idx,
                        status="approval_rejected",
                        errors=[rejection_error],
                    )
                    if attempt_idx >= max_attempts:
                        final_status = LoopFinalStatus.FAILED
                        stop_reason = "max_attempts_exhausted"
                        command_passed = False
                        break
                    continue

            if _is_aborted(abort_event=abort_event, is_aborted=is_aborted):
                _finish_attempt(record)
                final_status = LoopFinalStatus.ABORTED
                stop_reason = "user_abort"
                break

            _emit(
                on_event,
                "patch_start",
                attempt=attempt_idx,
            )
            if agent_response.mutation_baseline_ref is not None:
                # Direct-mutation provider: the agent already edited files on
                # disk. Do not re-`git apply` (it would conflict); the
                # captured diff already passed the adapter's post-hoc gate,
                # so re-derive touched files from the same pure check.
                validation = validate_patch_text(
                    agent_response.unified_diff,
                    max_files=max_files,
                    max_patch_kb=max_patch_kb,
                    reject_binary_changes=reject_binary,
                    sandbox_path=sandbox_path,
                )
                if validation.status == PatchApplyStatus.CHECKED_OK:
                    patch_result = PatchApplyResult(
                        status=PatchApplyStatus.APPLIED,
                        touched_files=list(validation.touched_files),
                    )
                else:
                    mutation_discarder(
                        sandbox_path, agent_response.mutation_baseline_ref
                    )
                    patch_result = validation
            else:
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
                errors=list(patch_result.errors),
            )

            _finish_attempt(record)

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
