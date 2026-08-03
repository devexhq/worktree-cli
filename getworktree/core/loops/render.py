"""Pure text formatters for human-readable loop show output."""

from __future__ import annotations

import json
from pathlib import Path

from getworktree.core.loops.models import LoopDefinition
from getworktree.core.loops.resolve import LoopResolveResult
from getworktree.core.loops.validate import LoopValidationResult


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


def format_loop_show_success(
    loop: LoopDefinition,
    *,
    source_path: Path,
    warnings: list[str] | None = None,
) -> str:
    """Return full success text including trailing newline.

    Args:
        loop: Validated loop definition.
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
        f"Loop: {loop.name}",
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
            _indent_block(loop.description),
            "",
            "Trigger:",
            f"  command: {loop.trigger.command}",
            f"  args: {_format_str_list(loop.trigger.args)}",
            f"  timeout_seconds: {loop.trigger.timeout_seconds}",
            "",
            "Agent:",
            f"  provider: {loop.agent.provider}",
            f"  mode: {loop.agent.mode}",
            f"  timeout_seconds: {loop.agent.timeout_seconds}",
            "",
            "Iteration:",
            f"  max_attempts: {loop.iteration.max_attempts}",
            f"  stop_when: {_format_str_list(list(loop.iteration.stop_when))}",
            "",
            "Sandbox:",
            f"  auto_clean: {_format_bool(loop.sandbox.auto_clean)}",
            f"  keep_on_failure: {_format_bool(loop.sandbox.keep_on_failure)}",
            "",
            "Approval:",
            f"  require_before_apply: {_format_bool(loop.approval.require_before_apply)}",
            "",
            "Context:",
            f"  include: {_format_str_list(list(loop.context.include))}",
            "",
            "Patch:",
            f"  strategy: {loop.patch.strategy}",
            f"  max_files: {loop.patch.max_files}",
            f"  max_patch_kb: {loop.patch.max_patch_kb}",
            "  reject_binary_changes: "
            f"{_format_optional_bool(loop.patch.reject_binary_changes)}",
        ]
    )
    return "\n".join(lines) + "\n"


def format_loop_show_resolve_failure(result: LoopResolveResult) -> str:
    """Return plain failure body text for a resolve failure.

    Args:
        result: Non-ok ``LoopResolveResult``.

    Returns:
        Joined resolve errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Failed to resolve loop."


def format_loop_show_validate_failure(result: LoopValidationResult) -> str:
    """Return plain failure body text for a validation failure.

    Args:
        result: Non-ok ``LoopValidationResult``.

    Returns:
        Joined validation errors, or a defensive fallback string.
    """
    if result.errors:
        return "\n\n".join(result.errors)
    return "Loop definition is invalid."
