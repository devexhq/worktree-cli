"""Pure text formatters for human-readable workflow show output."""

from __future__ import annotations

import json
from pathlib import Path

from getworktree.core.workflows.models import (
    LoopStepBlock,
    StandardStepDefinition,
    WorkflowDefinition,
)
from getworktree.core.workflows.resolve import WorkflowResolveResult
from getworktree.core.workflows.validate import WorkflowValidationResult


def _indent_block(text: str | None, *, prefix: str = "  ") -> str:
    if not text:
        return ""
    lines = text.splitlines() or [""]
    return "\n".join(f"{prefix}{line}" for line in lines)


def _format_warning_bullets(warnings: list[str]) -> list[str]:
    lines: list[str] = []
    for warning in warnings:
        parts = warning.splitlines() or [""]
        lines.append(f"- {parts[0]}")
        for continuation in parts[1:]:
            lines.append(f"  {continuation}")
    return lines


def format_workflow_show_success(
    workflow: WorkflowDefinition,
    *,
    source_path: Path,
    warnings: list[str] | None = None,
) -> str:
    """Return full success text including trailing newline.

    Args:
        workflow: Validated workflow definition.
        source_path: Absolute path to the definition file.
        warnings: Optional warning strings (resolve + validate).

    Returns:
        Plain-text success report with a trailing newline.
    """
    warning_list = list(warnings or [])
    status = "valid with warnings" if warning_list else "valid"
    abs_source = (
        source_path.as_posix()
        if source_path.is_absolute()
        else source_path.resolve().as_posix()
    )

    lines: list[str] = [
        f"Workflow: {workflow.name}",
        f"Source: {abs_source}",
        f"Status: {status}",
        "",
    ]
    if warning_list:
        lines.append("Warnings:")
        lines.extend(_format_warning_bullets(warning_list))
        lines.append("")

    if workflow.description:
        lines.extend(
            [
                "Description:",
                _indent_block(workflow.description),
                "",
            ]
        )

    if workflow.timeout_seconds:
        lines.append(f"Timeout: {workflow.timeout_seconds}s")
        lines.append("")

    if workflow.steps:
        lines.append("Steps:")
        for step in workflow.steps:
            if isinstance(step, LoopStepBlock):
                lines.append(f"  - id: {step.id}")
                lines.append("    type: loop")
                lines.append(f"    max_iterations: {step.max_iterations}")
                lines.append(f"    until: {json.dumps(step.until)}")
                lines.append("    do:")
                for sub in step.do:
                    lines.append(f"      - id: {sub.id}")
                    if sub.uses:
                        lines.append(f"        uses: {sub.uses}")
                    if sub.run:
                        lines.append(f"        run: {sub.run}")
            elif isinstance(step, StandardStepDefinition):
                step_id = step.id or step.name
                if step_id:
                    lines.append(f"  - id: {step_id}")
                if step.name and step.name != step_id:
                    lines.append(f"    name: {step.name}")
                if step.uses:
                    lines.append(f"    uses: {step.uses}")
                if step.run:
                    lines.append(f"    run: {step.run}")
                if step.prompt:
                    lines.append(f"    prompt: {step.prompt}")
                if step.timeout_seconds:
                    lines.append(f"    timeout_seconds: {step.timeout_seconds}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_workflow_show_resolve_failure(result: WorkflowResolveResult) -> str:
    """Return plain failure body text for a resolve failure.

    Args:
        result: Non-ok ``WorkflowResolveResult``.

    Returns:
        Joined resolve errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Failed to resolve workflow."


def format_workflow_show_validate_failure(result: WorkflowValidationResult) -> str:
    """Return plain failure body text for a validation failure.

    Args:
        result: Non-ok ``WorkflowValidationResult``.

    Returns:
        Joined validation errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Workflow definition is invalid."
