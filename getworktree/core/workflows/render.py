"""Pure text formatters for human-readable workflow show output."""

from __future__ import annotations

import json
from pathlib import Path

from getworktree.core.workflows.models import (
    StepReference,
    WorkflowDefinition,
)
from getworktree.core.workflows.resolve import WorkflowResolveResult
from getworktree.core.workflows.validate import WorkflowValidationResult


def _format_str_list(values: list[str]) -> str:
    """Render a string list as JSON-like text (``[]`` or ``["a", "b"]``)."""
    return json.dumps(values, ensure_ascii=False)


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "null"
    return _format_bool(value)


def _indent_block(text: str, *, prefix: str = "  ") -> str:
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

    lines.extend(
        [
            "Description:",
            _indent_block(workflow.description),
            "",
        ]
    )

    if workflow.steps:
        lines.append("Steps:")
        for step in workflow.steps:
            if isinstance(step, StepReference):
                lines.append(f"  - step_id: {step.step_id}")
                if step.override_timeout_seconds:
                    lines.append(
                        f"    override_timeout_seconds: {step.override_timeout_seconds}"
                    )
            else:
                lines.append(f"  - name: {step.name}")
                lines.append(f"    type: {step.type}")
                if step.command:
                    lines.append(f"    command: {step.command}")
                if step.prompt:
                    lines.append(f"    prompt: {step.prompt}")
                lines.append(f"    timeout_seconds: {step.timeout_seconds}")
        lines.append("")

    if workflow.trigger:
        lines.extend(
            [
                "Trigger:",
                f"  command: {workflow.trigger.command}",
                f"  args: {_format_str_list(workflow.trigger.args)}",
                f"  timeout_seconds: {workflow.trigger.timeout_seconds}",
                "",
            ]
        )

    if workflow.agent:
        lines.extend(
            [
                "Agent:",
                f"  provider: {workflow.agent.provider}",
                f"  mode: {workflow.agent.mode}",
                f"  timeout_seconds: {workflow.agent.timeout_seconds}",
                "",
            ]
        )

    lines.extend(
        [
            "Iteration:",
            f"  max_attempts: {workflow.iteration.max_attempts}",
            f"  stop_when: {_format_str_list(list(workflow.iteration.stop_when))}",
            "",
            "Sandbox:",
            f"  auto_clean: {_format_bool(workflow.sandbox.auto_clean)}",
            f"  keep_on_failure: {_format_bool(workflow.sandbox.keep_on_failure)}",
            "",
            "Approval:",
            f"  require_before_apply: {_format_bool(workflow.approval.require_before_apply)}",
            "",
            "Context:",
            f"  include: {_format_str_list(list(workflow.context.include))}",
            "",
            "Patch:",
            f"  strategy: {workflow.patch.strategy}",
            f"  max_files: {workflow.patch.max_files}",
            f"  max_patch_kb: {workflow.patch.max_patch_kb}",
            "  reject_binary_changes: "
            f"{_format_optional_bool(workflow.patch.reject_binary_changes)}",
        ]
    )
    return "\n".join(lines) + "\n"


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
