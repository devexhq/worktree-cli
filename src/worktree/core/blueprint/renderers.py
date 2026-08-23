"""Plain-text renderers for blueprint resolve, validate, and run failures."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from worktree.common.utils import RichOutput
from worktree.core.blueprint.models import BlueprintKind
from worktree.core.db import RunRecord
from worktree.core.runtime import RunOutcome


@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for turning a ``RunOutcome`` into plain text."""

    def render(self, outcome: RunOutcome) -> str:
        """Return a plain-text body for a run outcome."""
        ...


def _collect_primary_error(outcome: RunOutcome) -> str | None:
    if outcome.error_message:
        return outcome.error_message
    failed = [result.error_message for result in outcome.step_results if result.error_message]
    return "\n".join(failed) if failed else None


def _collect_step_output_details(outcome: RunOutcome) -> list[str]:
    details: list[str] = []
    primary = outcome.error_message or ""
    for result in outcome.step_results:
        if result.ok:
            continue
        text = (result.stderr or result.stdout or "").strip()
        if text and text not in primary:
            details.append(text)
    return details


class BlueprintRenderer:
    """Kind-aware plain-text formatter for blueprint failure bodies."""

    def __init__(self, kind: BlueprintKind) -> None:
        self.kind = kind

    def render(self, outcome: RunOutcome) -> str:
        """Return a plain-text body for a run failure."""
        parts: list[str] = []
        primary = _collect_primary_error(outcome)
        if primary:
            parts.append(primary)
        parts.extend(_collect_step_output_details(outcome))

        if parts:
            return "\n\n".join(parts)
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


def render_blueprint_run_success(
    run_record: RunRecord,
    kind: BlueprintKind | None = None,
    *,
    output: RichOutput,
) -> None:
    """Render blueprint run execution summary."""
    effective_kind = kind or run_record.kind
    label = effective_kind.value.capitalize() if effective_kind is not None else "Blueprint"
    output.info(
        f"[bold green]{label} Run Completed:[/] {run_record.blueprint_name} "
        f"(session: {run_record.session_id}, status: {run_record.status.value})"
    )
