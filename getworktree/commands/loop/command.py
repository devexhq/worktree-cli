"""Loop command handlers: show summaries and ``wt loop run`` orchestration."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from getworktree.commands.loop.renderers import (
    exit_code_for_status,
    format_run_output,
)
from getworktree.common.utils import RichOutput
from getworktree.core.config.loader import ConfigLoadStatus, load_config_result
from getworktree.core.loops.render import (
    format_loop_show_resolve_failure,
    format_loop_show_success,
    format_loop_show_validate_failure,
)
from getworktree.core.loops.resolve import resolve_loop_by_name
from getworktree.core.loops.runner import LoopRunResult, run_loop_iteration
from getworktree.core.loops.validate import validate_loop_result

rich_output = RichOutput()


def _format_warning_bullets(warnings: list[str]) -> list[str]:
    """Format engine warnings as bullet lines with indented continuations."""
    lines: list[str] = []
    for warning in warnings:
        parts = warning.splitlines() or [""]
        lines.append(f"- {parts[0]}")
        for continuation in parts[1:]:
            lines.append(f"  {continuation}")
    return lines


def loop_show_command(name: str, *, cwd: Path | None = None) -> None:
    """Resolve, validate, and print a human-readable loop summary.

    Read-only: does not mutate loop files, start sandboxes, or run triggers.
    Exit ``0`` when resolve and validate succeed (warnings allowed); exit ``1``
    on resolve or validate failure.

    Args:
        name: Logical loop name to show.
        cwd: Repository root. Defaults to process CWD.
    """
    root = (cwd or Path.cwd()).resolve()
    resolved = resolve_loop_by_name(name, cwd=root)

    if not resolved.ok:
        rich_output.error_panel(
            "Loop Show Failed",
            format_loop_show_resolve_failure(resolved),
        )
        raise typer.Exit(code=1)

    assert resolved.entry is not None
    validated = validate_loop_result(resolved.entry.source_path)

    if not validated.ok:
        rich_output.error_panel(
            "Loop Show Failed",
            format_loop_show_validate_failure(validated),
        )
        if resolved.warnings:
            warning_block = "Warnings:\n" + "\n".join(
                _format_warning_bullets(resolved.warnings)
            )
            rich_output.console.print(
                warning_block,
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        raise typer.Exit(code=1)

    assert validated.loop is not None
    warnings = [*resolved.warnings, *validated.warnings]
    payload = format_loop_show_success(
        validated.loop,
        source_path=validated.source_path,
        warnings=warnings,
    )
    rich_output.console.print(
        payload,
        end="",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    raise typer.Exit(code=0)


def _make_approve_callback(
    *,
    attempt_holder: dict[str, int],
) -> Callable[[str], bool]:
    """Build an approval callback using console input (non-TTY → deny)."""

    def approve_patch(diff: str) -> bool:
        _ = diff
        attempt = attempt_holder.get("attempt", 1)
        prompt = f"Apply agent patch for attempt {attempt}? [y/N]"
        if not sys.stdin.isatty():
            rich_output.info(prompt)
            rich_output.info("Non-interactive stdin: treating approval as rejected.")
            return False
        return bool(
            rich_output.console.input(prompt + " ").strip().lower() in {"y", "yes"}
        )

    return approve_patch


def loop_run_command(
    name: str,
    *,
    max_attempts: int | None = None,
    keep: bool | None = None,
    approve_each: bool | None = None,
    cwd: Path | None = None,
    run_loop_fn: Callable[..., LoopRunResult] | None = None,
) -> None:
    """Resolve a loop, run the iteration controller, render summary, exit.

    Args:
        name: Loop definition name.
        max_attempts: Optional ``--max-attempts`` override (≥1).
        keep: When True, force ``auto_clean=False``; when False/None, leave default.
        approve_each: When set, override loop approval.require_before_apply.
        cwd: Repository root.
        run_loop_fn: Injectable controller (tests); defaults to
            ``run_loop_iteration``.
    """
    root = (cwd or Path.cwd()).resolve()
    runner = run_loop_fn or run_loop_iteration

    if max_attempts is not None and max_attempts < 1:
        rich_output.error_panel(
            "Loop Run Failed",
            "--max-attempts must be an integer >= 1.",
        )
        raise typer.Exit(code=1)

    load = load_config_result(cwd=root)
    if load.status == ConfigLoadStatus.NOT_FOUND:
        rich_output.error_panel(
            "Loop Run Failed",
            load.errors[0]
            if load.errors
            else "Worktree is not initialized. Run `wt init`.",
        )
        raise typer.Exit(code=1)
    if not load.ok or load.config is None:
        detail = load.errors[0] if load.errors else "Invalid configuration."
        rich_output.error_panel("Loop Run Failed", detail)
        raise typer.Exit(code=1)

    config = load.config
    resolved = resolve_loop_by_name(name, cwd=root)
    if not resolved.ok:
        rich_output.error_panel(
            "Loop Run Failed",
            format_loop_show_resolve_failure(resolved),
        )
        raise typer.Exit(code=1)

    assert resolved.entry is not None
    validated = validate_loop_result(resolved.entry.source_path)
    if not validated.ok:
        rich_output.error_panel(
            "Loop Run Failed",
            format_loop_show_validate_failure(validated),
        )
        raise typer.Exit(code=1)

    assert validated.loop is not None
    loop = validated.loop

    auto_clean: bool | None = False if keep is True else None
    require_before_apply: bool | None = approve_each

    attempt_holder: dict[str, int] = {"attempt": 1}

    def on_event(event_name: str, payload: dict[str, Any]) -> None:
        if event_name == "attempt_start":
            attempt_holder["attempt"] = int(payload.get("attempt", 1))

    approve_cb = None
    effective_require = (
        require_before_apply
        if require_before_apply is not None
        else loop.approval.require_before_apply
    )
    if effective_require:
        approve_cb = _make_approve_callback(attempt_holder=attempt_holder)

    abort_event = threading.Event()
    result: LoopRunResult | None = None

    try:
        result = runner(
            loop=loop,
            cwd=root,
            config=config,
            caller_max_attempts=max_attempts,
            auto_clean=auto_clean,
            require_before_apply=require_before_apply,
            abort_event=abort_event,
            approve_patch=approve_cb,
            on_event=on_event,
            session_timeout_seconds=config.sandbox.default_timeout_seconds,
            detect_repeat_failures=config.loop.detect_repeat_failures,
        )
    except KeyboardInterrupt:
        abort_event.set()
        if result is None:
            rich_output.console.print(
                "Interrupted.\n",
                markup=False,
                highlight=False,
            )
            raise typer.Exit(code=130) from None

    assert result is not None
    if result.errors and result.stop_reason in {
        "sandbox_create_failed",
        "configuration_error",
    }:
        for err in result.errors:
            rich_output.error_panel("Loop Run Failed", err)

    text = format_run_output(result, cwd=root)
    rich_output.console.print(
        text,
        end="",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    raise typer.Exit(code=exit_code_for_status(result.status))
