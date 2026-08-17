"""Shared multi-step execution engine with optional sandbox lifecycle."""

from __future__ import annotations

from pathlib import Path

from worktree.core.db import RunStatus
from worktree.core.git_sandbox import GitSandboxManager, SandboxSession
from worktree.core.runtime.models import RunContext, RunOutcome
from worktree.core.step import StepDefinition, StepResult, execute_step


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
    detail = result.error_message or result.stderr or f"exit code {result.exit_code}"
    return f"Step '{result.step_id}' failed: {detail}"


def _build_step_context(context: RunContext) -> dict[str, object] | None:
    """Build the per-step execution context, including resolved inputs."""
    step_context: dict[str, object] = {}
    if context.agent:
        step_context["agent"] = context.agent
    if context.inputs:
        step_context["inputs"] = context.inputs
    return step_context or None


def _run_step_loop(context: RunContext, target_dir: Path) -> tuple[RunStatus, list[StepResult], str | None]:
    """Execute all steps, honoring failure policies and cancellation."""
    step_results: list[StepResult] = []
    total = len(context.steps)
    step_context = _build_step_context(context)

    try:
        for idx, step in enumerate(context.steps, start=1):
            _notify_step_start(context, idx, total, step)
            result = execute_step(step, sandbox_path=target_dir, context=step_context)
            _notify_step_done(context, idx, total, result)
            step_results.append(result)
            if not result.ok:
                return RunStatus.FAILED, step_results, _failed_step_message(result)
    except KeyboardInterrupt:
        return RunStatus.CANCELLED, step_results, "Execution cancelled by user."

    return RunStatus.COMPLETED, step_results, None


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
    sandbox_kept = False

    try:
        status, step_results, error_message = _run_step_loop(context, target_dir)
    finally:
        sandbox_kept = _cleanup_sandbox(context, manager, session, target_dir)

    return RunOutcome(
        status=status,
        step_results=step_results,
        error_message=error_message,
        sandbox_kept=sandbox_kept,
        sandbox_path=session.sandbox_path if session is not None else target_dir,
    )
