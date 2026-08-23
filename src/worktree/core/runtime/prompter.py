"""Interactive terminal adapter for runtime ``FailurePrompter``."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Literal

from worktree.common.utils import RichOutput
from worktree.core.runtime.models import FailurePromptDecision
from worktree.core.step import StepDefinition, StepResult

_CHOICE_MAP: dict[str, FailurePromptDecision] = {
    "r": FailurePromptDecision.RETRY,
    "retry": FailurePromptDecision.RETRY,
    "c": FailurePromptDecision.CONTINUE,
    "continue": FailurePromptDecision.CONTINUE,
    "a": FailurePromptDecision.ABORT,
    "abort": FailurePromptDecision.ABORT,
}


class CliFailurePrompter:
    """Rich/stdin adapter that maps ``r``/``c``/``a`` (and full words) to decisions."""

    def __init__(
        self,
        output: RichOutput,
        *,
        kind: Literal["task", "workflow"] | str = "task",
        input_fn: Callable[[str], str] | None = None,
        stdin_isatty: bool | None = None,
    ) -> None:
        self.output = output
        self.kind = kind
        self._input_fn = input_fn or input
        self._stdin_isatty = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty

    @property
    def is_interactive(self) -> bool:
        """Return whether this adapter can safely block on stdin."""
        return self._stdin_isatty

    def prompt_step_failure(
        self,
        *,
        step: StepDefinition,
        result: StepResult,
        diagnostic: str,
    ) -> FailurePromptDecision:
        """Print the failure prompt and return a validated user decision."""
        step_label = step.name or step.id
        self.output.add_line(f"Step '{step_label}' failed (exit code {result.exit_code}).")
        if diagnostic:
            self.output.add_line(diagnostic)
        self.output.add_line("")
        paused = "Task paused" if self.kind == "task" else "Workflow paused"
        self.output.add_line(f"{paused} waiting for user input.")
        self.output.add_line("")
        self.output.add_line("Options:")
        self.output.add_line("  [r] Retry step execution")
        self.output.add_line("  [c] Continue run (ignore failure)")
        self.output.add_line("  [a] Abort run")
        self.output.add_line("")
        return self._read_decision()

    def _read_decision(self) -> FailurePromptDecision:
        while True:
            try:
                raw = self._input_fn("Select option [r/c/a]: ")
            except EOFError:
                raw = ""
            choice = str(raw).strip().lower()
            decision = _CHOICE_MAP.get(choice)
            if decision is not None:
                return decision
            self.output.add_line("Invalid option. Enter r, c, or a (retry/continue/abort).")
