"""Task execution adapter over the shared runtime step engine."""

from __future__ import annotations

from pathlib import Path

from worktree.core.runtime import (
    FailurePrompter,
    RunContext,
    RunObserver,
    RunOutcome,
    RunPauseStore,
    run_steps,
)
from worktree.core.task.models import TaskDefinition


def run_task(
    definition: TaskDefinition,
    cwd: Path,
    *,
    use_sandbox: bool = True,
    keep: bool = False,
    agent: str | None = None,
    observer: RunObserver | None = None,
    inputs: dict[str, str | int | bool] | None = None,
    non_interactive: bool = False,
    failure_prompter: FailurePrompter | None = None,
    pause_store: RunPauseStore | None = None,
) -> RunOutcome:
    """Adapt ``TaskDefinition`` into ``RunContext`` and delegate to ``run_steps``."""
    context = RunContext(
        steps=definition.steps,
        cwd=cwd,
        use_sandbox=use_sandbox and definition.use_sandbox,
        keep=keep,
        agent=agent,
        observer=observer,
        inputs=inputs,
        non_interactive=non_interactive,
        failure_prompter=failure_prompter,
        pause_store=pause_store,
    )
    return run_steps(context)
