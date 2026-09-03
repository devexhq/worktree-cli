"""Interactive terminal adapter for runtime ``FailurePrompter``."""

from __future__ import annotations

import sys
from typing import Any, Literal

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
    """Terminal stdin adapter that maps ``r``/``c``/``a`` (and full words) to decisions."""

    def __init__(
        self,
        output: Any = None,
        *,
        kind: Literal["task", "workflow"] | str = "task",
    ) -> None:
        self.output = output
        self.kind = kind

    def _write_line(self, line: str) -> None:
        if self.output is not None:
            if hasattr(self.output, "add_line"):
                self.output.add_line(line)
            elif hasattr(self.output, "info"):
                self.output.info(line)
            elif hasattr(self.output, "print"):
                self.output.print(line)
            elif callable(self.output):
                self.output(line)

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
        self._write_line(f"Step '{step_label}' failed (exit code {result.exit_code}).")
        if diagnostic:
            self._write_line(diagnostic)
        self._write_line("")
        paused = "Task paused" if self.kind == "task" else "Workflow paused"
        self._write_line(f"{paused} waiting for user input.")
        self._write_line("")
        self._write_line("Options:")
        self._write_line("  \\[r] Retry step execution")
        self._write_line("  \\[c] Continue run (ignore failure)")
        self._write_line("  \\[a] Abort run")
        self._write_line("")
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
            self._write_line("Invalid option. Enter r, c, or a (retry/continue/abort).")

    def prompt_loop_max_iterations(
        self,
        *,
        loop: LoopStepBlock,
        iteration: int,
        diagnostic: str,
        grant_count: int = 3,
    ) -> LoopPromptDecision:
        """Print the loop max iterations prompt and return a validated user decision."""
        self._write_line(
            f"\\[{loop.id}] Reached max_iterations ({loop.max_iterations}) without meeting 'until' conditions."
        )
        self._write_line("Loop block paused.")
        self._write_line("")
        self._write_line("Options:")
        self._write_line(f"  \\[g] Grant {grant_count} additional iterations")
        self._write_line("  \\[c] Continue workflow past loop block")
        self._write_line("  \\[a] Abort workflow run")
        self._write_line("")
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
            self._write_line("Invalid option. Enter g, c, or a (grant/continue/abort).")
