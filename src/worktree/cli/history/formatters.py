"""ComponentFormatters for history CLI domain objects."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from worktree.cli.ui.dispatcher import UiDispatcher, ui_dispatcher
from worktree.common.types import ComponentFormatter
from worktree.core.db import RunRecord
from worktree.core.history.models import (
    HistoryListResult,
    HistoryListStatus,
    HistoryShowResult,
    HistoryShowStatus,
)
from worktree.core.history.renderers import (
    build_checkpoint_renderables,
    build_history_table,
    build_metadata_table,
)

_INVALID_CONFIG_INDICATORS = (
    "CONFIG_SCHEMA_INVALID",
    "CONFIG_MALFORMED_JSON",
    "CONFIG_ROOT_NOT_OBJECT",
    "PATH_IS_DIRECTORY",
    "CONFIG_UNREADABLE",
    "Config schema validation failed",
    "Malformed config.json",
)


def _render_history_not_initialized(errors: list[str]) -> Panel:
    """Render standardized not-initialized or invalid-config error panel."""
    if errors and any(any(indicator in error for indicator in _INVALID_CONFIG_INDICATORS) for error in errors):
        return Panel("\n\n".join(errors), title="Invalid Worktree Configuration", border_style="red")

    message = (
        "\n\n".join(errors)
        if errors
        else ".worktree/config.json not found.\nFix:\n- run `wt init` to initialize the workspace"
    )
    return Panel(message, title="Worktree Not Initialized", border_style="red")


def _render_list_runs(data: HistoryListResult) -> Any:
    """Render execution history runs table or empty text alongside optional warnings."""
    content: Any = build_history_table(data.runs) if data.runs else Text("No execution history found.")
    if not data.warnings:
        return content

    renderables: list[Any] = []
    for warning in data.warnings:
        renderables.append(Text.from_markup(f"[yellow]Warning:[/] {warning}"))
    renderables.append(content)
    return Group(*renderables)


class HistoryListFormatter(ComponentFormatter[HistoryListResult]):
    """Formatter for history list command results."""

    def to_rich(self, data: HistoryListResult) -> Any:
        """Render execution history table, warnings, or empty state.

        Args:
            data: Structured result of history list operation.

        Returns:
            Rich renderable object (Table, Group, Panel, or Text).
        """
        if data.status == HistoryListStatus.NOT_INITIALIZED or (not data.ok and data.errors):
            return _render_history_not_initialized(data.errors)

        return _render_list_runs(data)

    def to_json_serializable(self, data: HistoryListResult) -> dict[str, Any]:
        """Convert HistoryListResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of history list operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def _render_show_not_found(session_id: str | None) -> Panel:
    """Render error panel when requested session record is not found."""
    session_label = session_id or "unknown"
    message = f"Session '{session_label}' not found.\nFix:\n- run `wt history` to view past sessions"
    return Panel(message, title="Session Not Found", border_style="red")


def _render_show_error(errors: list[str]) -> Panel:
    """Render error panel when session show encounters errors."""
    return Panel("\n\n".join(errors), title="Session Show Failed", border_style="red")


def _render_show_error_panel(data: HistoryShowResult) -> Panel | None:
    """Check and render error panels for session show operation."""
    if data.status == HistoryShowStatus.NOT_INITIALIZED:
        return _render_history_not_initialized(data.errors)

    if data.status == HistoryShowStatus.NOT_FOUND or (data.run is None and not data.errors):
        return _render_show_not_found(data.session_id)

    if data.errors and not data.ok:
        return _render_show_error(data.errors)

    return None


def _render_show_run(run: RunRecord) -> Any:
    """Render detailed session metadata panel, error panel, and step timeline."""
    renderables: list[Any] = [
        Panel(
            build_metadata_table(run),
            title=f"Session Metadata: {run.session_id}",
            border_style="blue",
        )
    ]

    if run.error_message:
        renderables.append(Panel(run.error_message, title="Error Details", border_style="red"))

    if run.checkpoint_json:
        renderables.extend(build_checkpoint_renderables(run.checkpoint_json))

    return Group(*renderables) if len(renderables) > 1 else renderables[0]


class HistoryShowFormatter(ComponentFormatter[HistoryShowResult]):
    """Formatter for history show command results."""

    def to_rich(self, data: HistoryShowResult) -> Any:
        """Render detailed session metadata panel, error panel, and step timeline.

        Args:
            data: Structured result of history show operation.

        Returns:
            Rich renderable object (Panel, Group, or Text).
        """
        error_panel = _render_show_error_panel(data)
        if error_panel is not None:
            return error_panel

        if data.run is not None:
            return _render_show_run(data.run)

        return Text("")

    def to_json_serializable(self, data: HistoryShowResult) -> dict[str, Any]:
        """Convert HistoryShowResult to primitive dictionary for JSON serialization.

        Args:
            data: Structured result of history show operation.

        Returns:
            JSON-serializable dictionary.
        """
        return data.model_dump(mode="json")


def register_history_formatters(dispatcher: UiDispatcher | None = None) -> None:
    """Register all history ComponentFormatter instances on a UiDispatcher.

    Args:
        dispatcher: UiDispatcher instance to register on. Defaults to ui_dispatcher.
    """
    target = dispatcher if dispatcher is not None else ui_dispatcher
    target.register(HistoryListResult, HistoryListFormatter())
    target.register(HistoryShowResult, HistoryShowFormatter())


# Register default history formatters on the central ui_dispatcher
register_history_formatters()
