"""Interactive terminal adapter for runtime ``FailurePrompter``."""

from __future__ import annotations

import sys
from typing import Literal

from worktree.common.utils import RichOutput
from worktree.core.runtime.models import FailurePromptDecision, LoopPromptDecision
from worktree.core.step import LoopStepBlock, StepDefinition, StepResult

_CHOICE_MAP: dict[str, FailurePromptDecision] = {
    "r": FailurePromptDecision.RETRY,
    "retry": FailurePromptDecision.RETRY,
    "c": FailurePromptDecision.CONTINUE,
    "continue": FailurePromptDecision.CONTINUE,
    "a": FailurePromptDecision.ABORT,
    "abort": FailurePromptDecision.ABORT,
}

_LOOP_CHOICE_MAP: dict[str, LoopPromptDecision] = {
    "g": LoopPromptDecision.GRANT,
    "grant": LoopPromptDecision.GRANT,
    "c": LoopPromptDecision.CONTINUE,
    "continue": LoopPromptDecision.CONTINUE,
    "a": LoopPromptDecision.ABORT,
    "abort": LoopPromptDecision.ABORT,
}


class CliFailurePrompter:
    """Rich/stdin adapter that maps ``r``/``c``/``a`` (and full words) to decisions."""

    def __init__(
        self,
        output: RichOutput,
        *,
        kind: Literal["task", "workflow"] | str = "task",
    ) -> None:
        self.output = output
        self.kind = kind

    @property
    def is_interactive(self) -> bool:
        """Return whether this adapter can safely block on stdin."""
        return sys.stdin.isatty()

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
        self.output.add_line("  \\[r] Retry step execution")
        self.output.add_line("  \\[c] Continue run (ignore failure)")
        self.output.add_line("  \\[a] Abort run")
        self.output.add_line("")
        return self._read_decision()

    def _read_decision(self) -> FailurePromptDecision:
        while True:
            try:
                raw = input("Select option [r/c/a]: ")
            except EOFError:
                raw = ""
            choice = str(raw).strip().lower()
            decision = _CHOICE_MAP.get(choice)
            if decision is not None:
                return decision
            self.output.add_line("Invalid option. Enter r, c, or a (retry/continue/abort).")

    def prompt_loop_max_iterations(
        self,
        *,
        loop: LoopStepBlock,
        iteration: int,
        diagnostic: str,
        grant_count: int = 3,
    ) -> LoopPromptDecision:
        """Print the loop max iterations prompt and return a validated user decision."""
        self.output.add_line(
            f"\\[{loop.id}] Reached max_iterations ({loop.max_iterations}) without meeting 'until' conditions."
        )
        self.output.add_line("Loop block paused.")
        self.output.add_line("")
        self.output.add_line("Options:")
        self.output.add_line(f"  \\[g] Grant {grant_count} additional iterations")
        self.output.add_line("  \\[c] Continue workflow past loop block")
        self.output.add_line("  \\[a] Abort workflow run")
        self.output.add_line("")
        return self._read_loop_decision()

    def _read_loop_decision(self) -> LoopPromptDecision:
        while True:
            try:
                raw = input("Select option [g/c/a]: ")
            except EOFError:
                raw = ""
            choice = str(raw).strip().lower()
            decision = _LOOP_CHOICE_MAP.get(choice)
            if decision is not None:
                return decision
            self.output.add_line("Invalid option. Enter g, c, or a (grant/continue/abort).")
