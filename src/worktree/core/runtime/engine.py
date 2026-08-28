"""Shared multi-step execution engine with optional sandbox lifecycle."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import RunStatus, SandboxesRepository
from worktree.core.git_sandbox import GitSandboxManager, SandboxSession
from worktree.core.runtime.exceptions import PromptUserInterruptedError
from worktree.core.runtime.failure import (
    effective_terminal_policy,
    mark_continued_after_prompt,
    step_failure_diagnostic,
)
from worktree.core.runtime.models import (
    FailurePromptDecision,
    RunCheckpoint,
    RunContext,
    RunOutcome,
    StepLoopState,
)
from worktree.core.step import FailurePolicy, StepDefinition, StepResult, execute_step


def _notify_sandbox_ready(context: RunContext, path: Path, *, active: bool) -> None:
    if context.observer is not None:
        context.observer.on_sandbox_ready(path, active)


def _notify_step_start(context: RunContext, idx: int, total: int, step: StepDefinition) -> None:
    if context.observer is not None:
        context.observer.on_step_start(idx, total, step)


def _notify_step_output(
    context: RunContext,
    idx: int,
    total: int,
    step: StepDefinition,
    line: str,
    *,
    stream: str = "stdout",
) -> None:
    if context.observer is not None:
        context.observer.on_step_output(idx, total, step, line, stream=stream)


def _notify_step_done(context: RunContext, idx: int, total: int, result: StepResult) -> None:
    if context.observer is not None:
        context.observer.on_step_done(idx, total, result)


def _notify_sandbox_cleanup(context: RunContext, *, kept: bool, path: Path) -> None:
    if context.observer is not None:
        context.observer.on_sandbox_cleanup(kept, path)


def _session_from_checkpoint(checkpoint: RunCheckpoint, path: Path) -> SandboxSession:
    return SandboxSession(
        session_id=checkpoint.sandbox_id or "resumed",
        target_branch=checkpoint.sandbox_branch or "worktree/sandbox-resumed",
        sandbox_path=path,
        base_commit=checkpoint.sandbox_base_commit or "HEAD",
        name=checkpoint.sandbox_name,
        created_at="",
    )


def _setup_resumed_sandbox(
    context: RunContext,
    checkpoint: RunCheckpoint,
) -> tuple[Path, GitSandboxManager | None, SandboxSession | None, str | None]:
    if not checkpoint.use_sandbox:
        target_dir = context.cwd.resolve()
        _notify_sandbox_ready(context, target_dir, active=False)
        return target_dir, None, None, None

    path = Path(checkpoint.sandbox_path or "")
    if not path.exists():
        return context.cwd.resolve(), None, None, f"Git sandbox is missing: {path}"

    session = _session_from_checkpoint(checkpoint, path)
    manager = GitSandboxManager(context.cwd.resolve(), db=SandboxesRepository(context.cwd.resolve()))
    _notify_sandbox_ready(context, path, active=True)
    return path, manager, session, None


def _setup_sandbox(
    context: RunContext,
) -> tuple[Path, GitSandboxManager | None, SandboxSession | None, str | None]:
    """Create an optional sandbox and return the execution directory.

    Returns:
        Tuple of (target_dir, manager, session, error_message).
        ``error_message`` is set when sandbox setup fails.
    """
    if context.resume_from is not None:
        return _setup_resumed_sandbox(context, context.resume_from)

    if not context.use_sandbox:
        target_dir = context.cwd.resolve()
        _notify_sandbox_ready(context, target_dir, active=False)
        return target_dir, None, None, None

    manager = GitSandboxManager(context.cwd.resolve(), db=SandboxesRepository(context.cwd.resolve()))
    create_result = manager.create_sandbox_result()
    if not create_result.ok or create_result.session is None:
        detail = create_result.errors[0] if create_result.errors else "Sandbox creation failed."
        return context.cwd.resolve(), None, None, f"Git sandbox creation failed: {detail}"

    session = create_result.session
    target_dir = session.sandbox_path
    _notify_sandbox_ready(context, target_dir, active=True)
    return target_dir, manager, session, None


def _cleanup_sandbox(
    context: RunContext,
    manager: GitSandboxManager | None,
    session: SandboxSession | None,
    target_dir: Path,
) -> bool:
    """Clean up sandbox unless keep is requested. Returns whether it was kept."""
    if manager is None or session is None:
        _notify_sandbox_cleanup(context, kept=False, path=target_dir)
        return False

    if context.keep:
        _notify_sandbox_cleanup(context, kept=True, path=session.sandbox_path)
        return True

    try:
        manager.cleanup_sandbox(session)
    except Exception:
        # Best-effort cleanup: worktree removal is independent of run outcome.
        pass
    _notify_sandbox_cleanup(context, kept=False, path=session.sandbox_path)
    return False


def _failed_step_message(result: StepResult) -> str:
    detail = step_failure_diagnostic(result)
    return f"Step '{result.step_id}' failed: {detail}"


def _build_step_context(context: RunContext) -> dict[str, object] | None:
    """Build the per-step execution context, including resolved inputs."""
    step_context: dict[str, object] = {}
    if context.agent:
        step_context["agent"] = context.agent
    if context.inputs:
        step_context["inputs"] = context.inputs
    return step_context or None


def _build_checkpoint(
    context: RunContext,
    state: StepLoopState,
    *,
    step: StepDefinition,
    result: StepResult,
    step_index: int,
) -> RunCheckpoint:
    diagnostic = _failed_step_message(result)
    session = state.session
    return RunCheckpoint(
        next_step_index=step_index,
        step_results=list(state.step_results),
        sandbox_path=str(session.sandbox_path if session is not None else state.target_dir),
        sandbox_id=session.session_id if session is not None else None,
        sandbox_name=session.name if session is not None else None,
        sandbox_branch=session.target_branch if session is not None else None,
        sandbox_base_commit=session.base_commit if session is not None else None,
        use_sandbox=context.use_sandbox,
        keep=context.keep,
        agent=context.agent,
        inputs=dict(context.inputs or {}),
        pending_step_id=step.id,
        diagnostic=diagnostic,
        pending_result=result,
    )


def _try_save_checkpoint(context: RunContext, checkpoint: RunCheckpoint, warnings: list[str]) -> bool:
    if context.pause_store is None:
        return False
    try:
        context.pause_store.save_checkpoint(checkpoint)
    except Exception as exc:
        warnings.append(f"Failed to persist pause checkpoint: {exc}")
        return False
    return True


def _try_clear_pause(context: RunContext, warnings: list[str]) -> None:
    if context.pause_store is None:
        return
    try:
        context.pause_store.clear_pause()
    except Exception as exc:
        warnings.append(f"Failed to clear pause checkpoint: {exc}")


def _prompt_user_decision(
    context: RunContext,
    state: StepLoopState,
    step: StepDefinition,
    result: StepResult,
    step_index: int,
) -> tuple[FailurePromptDecision, str | None]:
    """Resolve a ``prompt_user`` decision, degrading to abort when non-interactive."""
    diagnostic = step_failure_diagnostic(result)
    if context.non_interactive or context.failure_prompter is None:
        if context.non_interactive:
            warning = f"Warning: step '{step.id}' requested prompt_user but the run is non-interactive; aborting."
        else:
            warning = (
                f"Warning: step '{step.id}' requested prompt_user but no failure prompter is configured; aborting."
            )
        return FailurePromptDecision.ABORT, warning

    checkpoint = _build_checkpoint(context, state, step=step, result=result, step_index=step_index)
    persisted = _try_save_checkpoint(context, checkpoint, state.warnings)
    try:
        decision = context.failure_prompter.prompt_step_failure(
            step=step,
            result=result,
            diagnostic=diagnostic,
        )
    except KeyboardInterrupt:
        if persisted:
            raise PromptUserInterruptedError(checkpoint.diagnostic) from None
        raise
    _try_clear_pause(context, state.warnings)
    return decision, None


def _apply_prompt_decision(
    decision: FailurePromptDecision,
    result: StepResult,
) -> tuple[str, StepResult | None, str | None]:
    """Map a prompt decision to orchestration action.

    Returns:
        ``(action, result_to_record, error_message)`` where action is one of
        ``retry``, ``continue``, ``abort``.
    """
    if decision == FailurePromptDecision.RETRY:
        return "retry", None, None
    if decision == FailurePromptDecision.CONTINUE:
        return "continue", mark_continued_after_prompt(result), None
    return "abort", result, _failed_step_message(result)


def _handle_failed_step(
    context: RunContext,
    state: StepLoopState,
    step: StepDefinition,
    result: StepResult,
    step_index: int,
) -> tuple[str, StepResult | None, str | None]:
    """Apply effective terminal policy for a failed step result.

    Returns:
        ``(action, result_to_record, error_message)`` where action is one of
        ``retry``, ``continue``, ``abort``.
    """
    policy = effective_terminal_policy(step.on_failure)
    if policy == FailurePolicy.CONTINUE:
        # Defensive: step-local continue already maps to ignored; treat as non-fatal.
        return "continue", mark_continued_after_prompt(result), None
    if policy == FailurePolicy.PROMPT_USER:
        decision, warning = _prompt_user_decision(context, state, step, result, step_index)
        if warning is not None:
            state.warnings.append(warning)
        return _apply_prompt_decision(decision, result)
    return "abort", result, _failed_step_message(result)


def _execute_one_step(
    context: RunContext,
    state: StepLoopState,
    step: StepDefinition,
    *,
    idx: int,
    total: int,
    step_index: int,
    step_context: dict[str, object] | None,
) -> tuple[str, StepResult | None, str | None]:
    """Run a step until success, continue-after-failure, or abort.

    Returns ``(action, result, error_message)`` with action ``continue`` or ``abort``.
    """
    while True:
        _notify_step_start(context, idx, total, step)
        result = execute_step(step, sandbox_path=state.target_dir, context=step_context)
        _notify_step_done(context, idx, total, result)
        if result.ok:
            return "continue", result, None
        action, recorded, error_message = _handle_failed_step(context, state, step, result, step_index)
        if action == "retry":
            continue
        return action, recorded, error_message


def _pending_result_for_resume(checkpoint: RunCheckpoint, step: StepDefinition) -> StepResult:
    if checkpoint.pending_result is not None:
        return checkpoint.pending_result
    return StepResult(
        step_id=step.id,
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        duration_seconds=0.0,
        error_message=checkpoint.diagnostic,
    )


def _resume_pending_gate(
    context: RunContext,
    state: StepLoopState,
    step: StepDefinition,
    checkpoint: RunCheckpoint,
    step_index: int,
) -> tuple[str, StepResult | None, str | None]:
    """Re-prompt at the paused step without re-executing it first."""
    result = _pending_result_for_resume(checkpoint, step)
    action, recorded, error_message = _handle_failed_step(context, state, step, result, step_index)
    if action != "retry":
        return action, recorded, error_message
    return _execute_one_step(
        context,
        state,
        step,
        idx=step_index + 1,
        total=len(context.steps),
        step_index=step_index,
        step_context=_build_step_context(context),
    )


def _dispatch_step(
    context: RunContext,
    state: StepLoopState,
    step: StepDefinition,
    step_index: int,
    step_context: dict[str, object] | None,
) -> tuple[str, StepResult | None, str | None]:
    """Run or re-prompt a step depending on whether this is the resume gate."""
    resume = context.resume_from
    if resume is not None and step_index == resume.next_step_index:
        return _resume_pending_gate(context, state, step, resume, step_index)
    return _execute_one_step(
        context,
        state,
        step,
        idx=step_index + 1,
        total=len(context.steps),
        step_index=step_index,
        step_context=step_context,
    )


def _run_remaining_steps(
    context: RunContext,
    state: StepLoopState,
    start: int,
) -> tuple[RunStatus, list[str]]:
    """Execute remaining steps from ``start`` until completion or abort."""
    step_context = _build_step_context(context)
    for step_index, step in enumerate(context.steps):
        if step_index < start:
            continue
        action, result, error_message = _dispatch_step(context, state, step, step_index, step_context)
        if result is not None:
            state.step_results.append(result)
        if action == "abort":
            errors = [error_message] if error_message else []
            return RunStatus.FAILED, errors
    return RunStatus.COMPLETED, []


def _run_step_loop(
    context: RunContext,
    state: StepLoopState,
) -> tuple[RunStatus, list[StepResult], list[str], list[str]]:
    """Execute all steps, honoring failure policies and cancellation."""
    start = context.resume_from.next_step_index if context.resume_from is not None else 0
    try:
        status, errors = _run_remaining_steps(context, state, start)
    except PromptUserInterruptedError as exc:
        errors = [str(exc)] if str(exc) else []
        return RunStatus.PAUSED, state.step_results, errors, state.warnings
    except KeyboardInterrupt:
        return RunStatus.CANCELLED, state.step_results, ["Execution cancelled by user."], state.warnings
    return status, state.step_results, errors, state.warnings


def run_steps(context: RunContext) -> RunOutcome:
    """Execute a sequence of steps under optional sandbox isolation and observer reporting.

    Args:
        context: Immutable run inputs including steps, cwd, and sandbox options.

    Returns:
        Classified outcome. Expected step/sandbox failures and cancellation are
        returned as structured status values rather than raised.
    """
    target_dir, manager, session, setup_error = _setup_sandbox(context)
    if setup_error is not None:
        return RunOutcome(
            status=RunStatus.FAILED,
            step_results=[],
            errors=[setup_error],
            sandbox_kept=False,
            sandbox_path=target_dir,
        )

    status: RunStatus = RunStatus.COMPLETED
    step_results: list[StepResult] = []
    errors: list[str] = []
    warnings: list[str] = []
    sandbox_kept = False
    prior = list(context.resume_from.step_results) if context.resume_from is not None else []
    state = StepLoopState(target_dir=target_dir, session=session, step_results=prior)

    try:
        status, step_results, errors, warnings = _run_step_loop(context, state)
    finally:
        if status == RunStatus.PAUSED:
            sandbox_kept = True
            kept_path = session.sandbox_path if session is not None else target_dir
            _notify_sandbox_cleanup(context, kept=True, path=kept_path)
        else:
            sandbox_kept = _cleanup_sandbox(context, manager, session, target_dir)

    return RunOutcome(
        status=status,
        step_results=step_results,
        errors=errors,
        warnings=warnings,
        sandbox_kept=sandbox_kept,
        sandbox_path=session.sandbox_path if session is not None else target_dir,
    )
