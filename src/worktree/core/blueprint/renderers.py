"""Plain-text renderers for blueprint resolve, validate, and run failures."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from worktree.common.utils import RichOutput
from worktree.core.blueprint.models import BlueprintKind
from worktree.core.db import RunRecord
from worktree.core.step import StepResult


@runtime_checkable
class RenderableRunOutcome(Protocol):
    """Structural protocol for run outcomes accepted by plain-text renderers."""

    @property
    def errors(self) -> Sequence[str]:
        """Top-level failure or summary error messages."""
        ...

    @property
    def step_results(self) -> Sequence[StepResult]:
        """Ordered sequence of executed step results."""
        ...


@runtime_checkable
class Renderer(Protocol):
    """Structural protocol for turning a run outcome into plain text."""

    def render(self, outcome: RenderableRunOutcome) -> str:
        """Return a plain-text body for a run outcome."""
        ...


def _collect_primary_error(outcome: RenderableRunOutcome) -> str | None:
    if outcome.errors:
        return "\n".join(outcome.errors)
    failed = [result.error_message for result in outcome.step_results if result.error_message]
    return "\n".join(failed) if failed else None


def _collect_step_output_details(outcome: RenderableRunOutcome) -> list[str]:
    details: list[str] = []
    primary = "\n".join(outcome.errors) if outcome.errors else ""
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

    def render(self, outcome: RenderableRunOutcome) -> str:
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
    output.add_line(
        f"[bold green]{label} Run Completed:[/] {run_record.blueprint_name} "
        f"(session: {run_record.session_id}, status: {run_record.status.value})"
    )
