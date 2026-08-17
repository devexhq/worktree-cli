"""Shared multi-step execution engine with optional sandbox lifecycle."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import RunStatus
from worktree.core.git_sandbox import GitSandboxManager, SandboxSession
from worktree.core.runtime.failure import (
    FailurePromptDecision,
    effective_terminal_policy,
    mark_continued_after_prompt,
    step_failure_diagnostic,
)
from worktree.core.runtime.models import RunContext, RunOutcome
from worktree.core.step import FailurePolicy, StepDefinition, StepResult, execute_step


def _notify_sandbox_ready(context: RunContext, path: Path, *, active: bool) -> None:
    if context.observer is not None:
        context.observer.on_sandbox_ready(path, active)


def _notify_step_start(context: RunContext, idx: int, total: int, step: StepDefinition) -> None:
    if context.observer is not None:
        context.observer.on_step_start(idx, total, step)


def _notify_step_done(context: RunContext, idx: int, total: int, result: StepResult) -> None:
    if context.observer is not None:
        context.observer.on_step_done(idx, total, result)


def _notify_sandbox_cleanup(context: RunContext, *, kept: bool, path: Path) -> None:
    if context.observer is not None:
        context.observer.on_sandbox_cleanup(kept, path)


def _setup_sandbox(
    context: RunContext,
) -> tuple[Path, GitSandboxManager | None, SandboxSession | None, str | None]:
    """Create an optional sandbox and return the execution directory.

    Returns:
        Tuple of (target_dir, manager, session, error_message).
        ``error_message`` is set when sandbox setup fails.
    """
    if not context.use_sandbox:
        target_dir = context.cwd.resolve()
        _notify_sandbox_ready(context, target_dir, active=False)
        return target_dir, None, None, None

    manager = GitSandboxManager(cwd=context.cwd.resolve())
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


def _prompt_user_decision(
    context: RunContext,
    step: StepDefinition,
    result: StepResult,
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

    if context.pause_hook is not None:
        context.pause_hook.on_pause(step=step, result=result)
    decision = context.failure_prompter.prompt_step_failure(
        step=step,
        result=result,
        diagnostic=diagnostic,
    )
    if context.pause_hook is not None:
        context.pause_hook.on_resume(step=step, decision=decision)
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
    step: StepDefinition,
    result: StepResult,
    warnings: list[str],
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
        decision, warning = _prompt_user_decision(context, step, result)
        if warning is not None:
            warnings.append(warning)
        return _apply_prompt_decision(decision, result)
    return "abort", result, _failed_step_message(result)


def _execute_one_step(
    context: RunContext,
    step: StepDefinition,
    *,
    idx: int,
    total: int,
    target_dir: Path,
    step_context: dict[str, object] | None,
    warnings: list[str],
) -> tuple[str, StepResult | None, str | None]:
    """Run a step until success, continue-after-failure, or abort.

    Returns ``(action, result, error_message)`` with action ``continue`` or ``abort``.
    """
    while True:
        _notify_step_start(context, idx, total, step)
        result = execute_step(step, sandbox_path=target_dir, context=step_context)
        _notify_step_done(context, idx, total, result)
        if result.ok:
            return "continue", result, None
        action, recorded, error_message = _handle_failed_step(context, step, result, warnings)
        if action == "retry":
            continue
        return action, recorded, error_message


def _run_step_loop(
    context: RunContext,
    target_dir: Path,
) -> tuple[RunStatus, list[StepResult], str | None, list[str]]:
    """Execute all steps, honoring failure policies and cancellation."""
    step_results: list[StepResult] = []
    warnings: list[str] = []
    total = len(context.steps)
    step_context = _build_step_context(context)

    try:
        for idx, step in enumerate(context.steps, start=1):
            action, result, error_message = _execute_one_step(
                context,
                step,
                idx=idx,
                total=total,
                target_dir=target_dir,
                step_context=step_context,
                warnings=warnings,
            )
            if result is not None:
                step_results.append(result)
            if action == "abort":
                return RunStatus.FAILED, step_results, error_message, warnings
    except KeyboardInterrupt:
        return RunStatus.CANCELLED, step_results, "Execution cancelled by user.", warnings

    return RunStatus.COMPLETED, step_results, None, warnings


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
            error_message=setup_error,
            sandbox_kept=False,
            sandbox_path=target_dir,
        )

    status: RunStatus = RunStatus.COMPLETED
    step_results: list[StepResult] = []
    error_message: str | None = None
    warnings: list[str] = []
    sandbox_kept = False

    try:
        status, step_results, error_message, warnings = _run_step_loop(context, target_dir)
    finally:
        sandbox_kept = _cleanup_sandbox(context, manager, session, target_dir)

    return RunOutcome(
        status=status,
        step_results=step_results,
        error_message=error_message,
        warnings=warnings,
        sandbox_kept=sandbox_kept,
        sandbox_path=session.sandbox_path if session is not None else target_dir,
    )
