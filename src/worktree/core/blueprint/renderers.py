"""Plain-text renderers for blueprint resolve, validate, and run failures."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from worktree.core.blueprint.models import BlueprintKind
from worktree.core.runtime import RunOutcome


@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for turning a ``RunOutcome`` into plain text."""

    def render(self, outcome: RunOutcome) -> str:
        """Return a plain-text body for a run outcome."""
        ...


class BlueprintRenderer:
    """Kind-aware plain-text formatter for blueprint failure bodies."""

    def __init__(self, kind: BlueprintKind) -> None:
        self.kind = kind

    def render(self, outcome: RunOutcome) -> str:
        """Return a plain-text body for a run failure."""
        if outcome.error_message:
            return outcome.error_message

        failed_messages = [result.error_message for result in outcome.step_results if result.error_message]
        if failed_messages:
            return "\n".join(failed_messages)

        return f"{self.kind.value.capitalize()} execution failed."

    def render_resolve_failure(self, errors: list[str]) -> str:
        """Return a plain-text body for a catalog resolve failure."""
        if errors:
            return "\n\n".join(errors)
        return f"Failed to resolve {self.kind.value}."

    def render_validate_failure(self, errors: list[str]) -> str:
        """Return a plain-text body for a definition validation failure."""
        if errors:
            return "\n\n".join(errors)
        return f"{self.kind.value.capitalize()} definition is invalid."
